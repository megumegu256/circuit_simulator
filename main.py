"""
Circuit Simulator - 論理回路シミュレータ (将来的に量子回路もサポート予定)

このプログラムは、視覚的な論理回路シミュレータを提供します。
ユーザーはドラッグ&ドロップで論理ゲートを配置し、配線して回路を構築できます。

主な機能:
- 基本論理ゲート (AND, OR, NOT, NAND, NOR, XOR, XNOR) のサポート
- ドラッグ&ドロップによるゲート配置と配線
- シミュレーション実行と結果の視覚的表示
- 回路の保存/読み込み (JSON形式)
- 画像エクスポート機能
- 自動配置整列機能
- 設定管理 (config.json)
- Undo/Redo 機能
- ズームイン・ズームアウト
- 複数回路のタブ管理
- ステップ実行機能
- シミュレーション履歴表示
- ショートカットキーカスタマイズ

使用方法:
python main.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, Menu, simpledialog
import json
import os
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any, Callable
from enum import Enum
from abc import ABC, abstractmethod
import math
from copy import deepcopy
from collections import deque
import matplotlib
matplotlib.use('TkAgg')
# 日本語フォント設定
matplotlib.rcParams['font.sans-serif'] = ['Yu Gothic', 'Hiragino Sans', 'DejaVu Sans']
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


# ========== 定数定義 ==========
CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 800
GATE_WIDTH = 80
GATE_HEIGHT = 60
PIN_RADIUS = 5
GRID_SIZE = 20
MAX_HISTORY = 50  # Undo/Redo 履歴の最大数
DEFAULT_ZOOM = 1.0
MAX_ZOOM = 3.0
MIN_ZOOM = 0.3
ZOOM_STEP = 0.1

DEFAULT_CONFIG = {
    "theme": "light",
    "grid_enabled": True,
    "snap_to_grid": True,
    "auto_save": True,
    "canvas_width": CANVAS_WIDTH,
    "canvas_height": CANVAS_HEIGHT,
    "last_project": "",
    "shortcuts": {
        "undo": "<Control-z>",
        "redo": "<Control-y>",
        "new": "<Control-n>",
        "open": "<Control-o>",
        "save": "<Control-s>",
        "zoom_in": "<Control-plus>",
        "zoom_out": "<Control-minus>",
        "delete": "<Delete>",
        "copy": "<Control-c>",
        "paste": "<Control-v>",
        "auto_arrange": "<Control-a>"
    }
}


# ========== 回路タイプ列挙型 ==========
class CircuitType(Enum):
    """回路のタイプを定義"""
    LOGIC = "logic"  # 論理回路
    QUANTUM = "quantum"  # 量子回路 (将来実装予定)


# ========== 信号状態 ==========
class SignalState(Enum):
    """信号の状態"""
    LOW = 0
    HIGH = 1
    UNDEFINED = -1


# ========== 時間単位 ==========
class TimeUnit(Enum):
    """時間の単位"""
    SECONDS = ("s", 1.0)
    MILLISECONDS = ("ms", 1e-3)
    MICROSECONDS = ("μs", 1e-6)
    NANOSECONDS = ("ns", 1e-9)
    
    def __init__(self, symbol: str, multiplier: float):
        self.symbol = symbol
        self.multiplier = multiplier
    
    @staticmethod
    def from_symbol(symbol: str) -> 'TimeUnit':
        """記号から時間単位を取得"""
        for unit in TimeUnit:
            if unit.symbol == symbol:
                return unit
        return TimeUnit.SECONDS


# ========== Command パターン (Undo/Redo) ==========
class Command(ABC):
    """Undo/Redo のためのコマンド基底クラス"""
    
    @abstractmethod
    def execute(self):
        """コマンドを実行"""
        pass
    
    @abstractmethod
    def undo(self):
        """コマンドを元に戻す"""
        pass


class AddComponentCommand(Command):
    """コンポーネント追加コマンド"""
    
    def __init__(self, circuit: 'Circuit', component: 'Component'):
        self.circuit = circuit
        self.component = component
    
    def execute(self):
        self.circuit.components[self.component.id] = self.component
    
    def undo(self):
        if self.component.id in self.circuit.components:
            del self.circuit.components[self.component.id]


class RemoveComponentCommand(Command):
    """コンポーネント削除コマンド"""
    
    def __init__(self, circuit: 'Circuit', comp_id: str):
        self.circuit = circuit
        self.comp_id = comp_id
        self.component = None
        self.related_wires = []
    
    def execute(self):
        if self.comp_id in self.circuit.components:
            self.component = deepcopy(self.circuit.components[self.comp_id])
            self.related_wires = [
                (wire_id, deepcopy(wire)) for wire_id, wire in self.circuit.wires.items()
                if wire.from_comp == self.comp_id or wire.to_comp == self.comp_id
            ]
            self.circuit.remove_component(self.comp_id)
    
    def undo(self):
        if self.component:
            self.circuit.components[self.component.id] = self.component
            for wire_id, wire in self.related_wires:
                self.circuit.wires[wire_id] = wire


class AddWireCommand(Command):
    """配線追加コマンド"""
    
    def __init__(self, circuit: 'Circuit', wire: 'Wire'):
        self.circuit = circuit
        self.wire = wire
    
    def execute(self):
        self.circuit.wires[self.wire.wire_id] = self.wire
    
    def undo(self):
        if self.wire.wire_id in self.circuit.wires:
            del self.circuit.wires[self.wire.wire_id]


class RemoveWireCommand(Command):
    """配線削除コマンド"""
    
    def __init__(self, circuit: 'Circuit', wire_id: str):
        self.circuit = circuit
        self.wire_id = wire_id
        self.wire = None
    
    def execute(self):
        if self.wire_id in self.circuit.wires:
            self.wire = deepcopy(self.circuit.wires[self.wire_id])
            del self.circuit.wires[self.wire_id]
    
    def undo(self):
        if self.wire:
            self.circuit.wires[self.wire_id] = self.wire


class MoveComponentCommand(Command):
    """コンポーネント移動コマンド"""
    
    def __init__(self, component: 'Component', old_x: float, old_y: float, new_x: float, new_y: float):
        self.component = component
        self.old_x = old_x
        self.old_y = old_y
        self.new_x = new_x
        self.new_y = new_y
    
    def execute(self):
        self.component.x = self.new_x
        self.component.y = self.new_y
    
    def undo(self):
        self.component.x = self.old_x
        self.component.y = self.old_y


# ========== 基底クラス定義 ==========
class Component(ABC):
    """全てのコンポーネント(ゲート)の基底クラス"""
    
    def __init__(self, x: float, y: float, comp_id: str, name: Optional[str] = None):
        self.x = x
        self.y = y
        self.id = comp_id
        self.name = name if name else comp_id
        self.inputs: List[Optional[SignalState]] = []
        self.output: Optional[SignalState] = SignalState.UNDEFINED
        
    @abstractmethod
    def compute(self) -> SignalState:
        """出力を計算する"""
        pass
    
    @abstractmethod
    def get_type(self) -> str:
        """コンポーネントのタイプを返す"""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "type": self.get_type(),
            "id": self.id,
            "name": self.name,
            "x": self.x,
            "y": self.y
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Component':
        """辞書からコンポーネントを生成"""
        gate_type = data["type"]
        x, y = data["x"], data["y"]
        comp_id = data["id"]
        name = data.get("name", comp_id)
        
        gate_classes = {
            "AND": ANDGate,
            "OR": ORGate,
            "NOT": NOTGate,
            "NAND": NANDGate,
            "NOR": NORGate,
            "XOR": XORGate,
            "XNOR": XNORGate,
            "INPUT": InputSource,
            "OUTPUT": OutputDisplay
        }
        
        if gate_type == "INPUT":
            comp = InputSource(x, y, comp_id, name=name)
            comp.apply_pulse_settings(data)
            if "state" in data:
                comp.set_state(SignalState(data["state"]))
            return comp
        if gate_type == "OUTPUT":
            return OutputDisplay(x, y, comp_id, name=name)
        if gate_type in gate_classes:
            return gate_classes[gate_type](x, y, comp_id, name=name)
        else:
            raise ValueError(f"Unknown gate type: {gate_type}")


# ========== 論理ゲート実装 ==========
class LogicGate(Component):
    """論理ゲートの基底クラス"""
    
    def __init__(self, x: float, y: float, comp_id: str, num_inputs: int, name: Optional[str] = None):
        super().__init__(x, y, comp_id, name=name)
        self.inputs = [SignalState.UNDEFINED] * num_inputs


class ANDGate(LogicGate):
    """ANDゲート"""
    
    def __init__(self, x: float, y: float, comp_id: str, name: Optional[str] = None):
        super().__init__(x, y, comp_id, 2, name=name)
    
    def compute(self) -> SignalState:
        if SignalState.UNDEFINED in self.inputs:
            self.output = SignalState.UNDEFINED
        else:
            self.output = SignalState.HIGH if all(inp == SignalState.HIGH for inp in self.inputs) else SignalState.LOW
        return self.output
    
    def get_type(self) -> str:
        return "AND"


class ORGate(LogicGate):
    """ORゲート"""
    
    def __init__(self, x: float, y: float, comp_id: str, name: Optional[str] = None):
        super().__init__(x, y, comp_id, 2, name=name)
    
    def compute(self) -> SignalState:
        if SignalState.UNDEFINED in self.inputs:
            self.output = SignalState.UNDEFINED
        else:
            self.output = SignalState.HIGH if any(inp == SignalState.HIGH for inp in self.inputs) else SignalState.LOW
        return self.output
    
    def get_type(self) -> str:
        return "OR"


class NOTGate(LogicGate):
    """NOTゲート"""
    
    def __init__(self, x: float, y: float, comp_id: str, name: Optional[str] = None):
        super().__init__(x, y, comp_id, 1, name=name)
    
    def compute(self) -> SignalState:
        if self.inputs[0] == SignalState.UNDEFINED:
            self.output = SignalState.UNDEFINED
        else:
            self.output = SignalState.LOW if self.inputs[0] == SignalState.HIGH else SignalState.HIGH
        return self.output
    
    def get_type(self) -> str:
        return "NOT"


class NANDGate(LogicGate):
    """NANDゲート"""
    
    def __init__(self, x: float, y: float, comp_id: str, name: Optional[str] = None):
        super().__init__(x, y, comp_id, 2, name=name)
    
    def compute(self) -> SignalState:
        if SignalState.UNDEFINED in self.inputs:
            self.output = SignalState.UNDEFINED
        else:
            self.output = SignalState.LOW if all(inp == SignalState.HIGH for inp in self.inputs) else SignalState.HIGH
        return self.output
    
    def get_type(self) -> str:
        return "NAND"


class NORGate(LogicGate):
    """NORゲート"""
    
    def __init__(self, x: float, y: float, comp_id: str, name: Optional[str] = None):
        super().__init__(x, y, comp_id, 2, name=name)
    
    def compute(self) -> SignalState:
        if SignalState.UNDEFINED in self.inputs:
            self.output = SignalState.UNDEFINED
        else:
            self.output = SignalState.LOW if any(inp == SignalState.HIGH for inp in self.inputs) else SignalState.HIGH
        return self.output
    
    def get_type(self) -> str:
        return "NOR"


class XORGate(LogicGate):
    """XORゲート"""
    
    def __init__(self, x: float, y: float, comp_id: str, name: Optional[str] = None):
        super().__init__(x, y, comp_id, 2, name=name)
    
    def compute(self) -> SignalState:
        if SignalState.UNDEFINED in self.inputs:
            self.output = SignalState.UNDEFINED
        else:
            high_count = sum(1 for inp in self.inputs if inp == SignalState.HIGH)
            self.output = SignalState.HIGH if high_count == 1 else SignalState.LOW
        return self.output
    
    def get_type(self) -> str:
        return "XOR"


class XNORGate(LogicGate):
    """XNORゲート"""
    
    def __init__(self, x: float, y: float, comp_id: str, name: Optional[str] = None):
        super().__init__(x, y, comp_id, 2, name=name)
    
    def compute(self) -> SignalState:
        if SignalState.UNDEFINED in self.inputs:
            self.output = SignalState.UNDEFINED
        else:
            high_count = sum(1 for inp in self.inputs if inp == SignalState.HIGH)
            self.output = SignalState.LOW if high_count == 1 else SignalState.HIGH
        return self.output
    
    def get_type(self) -> str:
        return "XNOR"


class InputSource(Component):
    """入力ソース"""
    
    def __init__(self, x: float, y: float, comp_id: str, name: Optional[str] = None):
        super().__init__(x, y, comp_id, name=name)
        self.output = SignalState.LOW
        self.pulse_enabled = True  # パルスは常に有効
        # 時間ベースのパルス設定
        self.pulse_period = 1.0  # 周期（時間単位での値）
        self.pulse_period_unit = TimeUnit.MILLISECONDS  # 周期の単位
        self.pulse_duty_cycle = 0.5  # デューティサイクル（0.0-1.0）
        self.pulse_phase = 0.0  # 位相（時間単位での値）
        self.pulse_phase_unit = TimeUnit.MILLISECONDS  # 位相の単位
        # 後方互換性のためのステップベース設定
        self.pulse_period_steps = 4
        self.pulse_phase_steps = 0
    
    def compute(self) -> SignalState:
        return self.output
    
    def toggle(self):
        """入力を切り替える"""
        self.pulse_enabled = False
        self.output = SignalState.HIGH if self.output == SignalState.LOW else SignalState.LOW
    
    def set_state(self, state: SignalState):
        """状態を設定する"""
        self.pulse_enabled = False
        self.output = state
    
    def get_type(self) -> str:
        return "INPUT"

    def update_pulse(self, step_index: int, time_step: float = None):
        """パルス設定に従って出力を更新
        
        Args:
            step_index: ステップインデックス
            time_step: 1ステップあたりの時間（秒単位）。Noneの場合はステップベースで計算
        """
        if not self.pulse_enabled:
            return
        
        if time_step is not None:
            # 時間ベースの計算
            current_time = step_index * time_step
            period_sec = self.pulse_period * self.pulse_period_unit.multiplier
            phase_sec = self.pulse_phase * self.pulse_phase_unit.multiplier
            duty = max(0.0, min(1.0, float(self.pulse_duty_cycle)))
            
            position = (current_time + phase_sec) % period_sec
            threshold = period_sec * duty
            self.output = SignalState.HIGH if position < threshold else SignalState.LOW
        else:
            # ステップベース（後方互換性）
            period = max(1, int(self.pulse_period_steps))
            duty = max(0.0, min(1.0, float(self.pulse_duty_cycle)))
            phase = int(self.pulse_phase_steps)
            position = (step_index + phase) % period
            threshold = int(round(period * duty))
            self.output = SignalState.HIGH if position < threshold else SignalState.LOW

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            "state": self.output.value if self.output is not None else SignalState.UNDEFINED.value,
            "pulse_enabled": self.pulse_enabled,
            "pulse_period": self.pulse_period,
            "pulse_period_unit": self.pulse_period_unit.symbol,
            "pulse_duty_cycle": self.pulse_duty_cycle,
            "pulse_phase": self.pulse_phase,
            "pulse_phase_unit": self.pulse_phase_unit.symbol,
            # 後方互換性
            "pulse_period_steps": self.pulse_period_steps,
            "pulse_phase_steps": self.pulse_phase_steps
        })
        return data

    def apply_pulse_settings(self, data: Dict[str, Any]):
        self.pulse_enabled = data.get("pulse_enabled", True)  # デフォルトはTrue（常に有効）
        # 新しい時間ベース設定
        self.pulse_period = data.get("pulse_period", 1.0)
        self.pulse_period_unit = TimeUnit.from_symbol(data.get("pulse_period_unit", "ms"))
        self.pulse_duty_cycle = data.get("pulse_duty_cycle", 0.5)
        self.pulse_phase = data.get("pulse_phase", 0.0)
        self.pulse_phase_unit = TimeUnit.from_symbol(data.get("pulse_phase_unit", "ms"))
        # 後方互換性
        self.pulse_period_steps = data.get("pulse_period_steps", 4)
        self.pulse_phase_steps = data.get("pulse_phase_steps", 0)


class OutputDisplay(Component):
    """出力ディスプレイ"""
    
    def __init__(self, x: float, y: float, comp_id: str, name: Optional[str] = None):
        super().__init__(x, y, comp_id, name=name)
        self.inputs = [SignalState.UNDEFINED]
        self.history: List[SignalState] = []
    
    def compute(self) -> SignalState:
        self.output = self.inputs[0]
        return self.output
    
    def get_type(self) -> str:
        return "OUTPUT"

    def record_state(self):
        self.history.append(self.output if self.output is not None else SignalState.UNDEFINED)

    def clear_history(self):
        self.history.clear()


# ========== 配線クラス ==========
@dataclass
class Wire:
    """配線を表すクラス"""
    wire_id: str
    from_comp: str  # 出力元コンポーネントID
    to_comp: str    # 入力先コンポーネントID
    to_input_index: int  # 入力先のインデックス
    points: List[Tuple[float, float]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "id": self.wire_id,
            "from": self.from_comp,
            "to": self.to_comp,
            "to_input_index": self.to_input_index,
            "points": self.points
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Wire':
        """辞書から配線を生成"""
        return Wire(
            wire_id=data["id"],
            from_comp=data["from"],
            to_comp=data["to"],
            to_input_index=data["to_input_index"],
            points=data.get("points", [])
        )


# ========== シミュレーション履歴クラス ==========
@dataclass
class SimulationStep:
    """シミュレーションの1ステップを表すクラス"""
    step_number: int
    component_states: Dict[str, SignalState]  # {comp_id: output_state}
    timestamp: float = 0.0


# ========== 回路クラス ==========
class Circuit:
    """回路全体を管理するクラス"""
    
    def __init__(self, circuit_type: CircuitType = CircuitType.LOGIC):
        self.circuit_type = circuit_type
        self.components: Dict[str, Component] = {}
        self.wires: Dict[str, Wire] = {}
        self.next_comp_id = 1
        self.next_wire_id = 1
        self.simulation_history: List[SimulationStep] = []
        self.current_step = 0
        self.last_time_step = 0.001  # 最後のシミュレーションで使用した時間ステップ（秘位）
    
    def add_component(self, component: Component) -> str:
        """コンポーネントを追加"""
        self.components[component.id] = component
        return component.id
    
    def remove_component(self, comp_id: str):
        """コンポーネントを削除"""
        # 関連する配線も削除
        wires_to_remove = [
            wire_id for wire_id, wire in self.wires.items()
            if wire.from_comp == comp_id or wire.to_comp == comp_id
        ]
        for wire_id in wires_to_remove:
            del self.wires[wire_id]
        
        if comp_id in self.components:
            del self.components[comp_id]
    
    def add_wire(self, wire: Wire) -> str:
        """配線を追加"""
        self.wires[wire.wire_id] = wire
        return wire.wire_id
    
    def remove_wire(self, wire_id: str):
        """配線を削除"""
        if wire_id in self.wires:
            del self.wires[wire_id]
    
    def simulate(self, step_by_step: bool = False, steps: int = 1, time_step: float = None):
        """シミュレーションを実行
        
        Args:
            step_by_step: ステップ実行モード
            steps: 実行ステップ数
            time_step: 1ステップあたりの時間（秒単位）。Noneの場合はステップベース
        """
        # トポロジカルソートを行い、依存関係を解決
        visited = set()
        processing = set()
        order = []
        
        def visit(comp_id: str):
            """深さ優先探索でトポロジカルソート"""
            if comp_id in visited:
                return
            if comp_id in processing:
                # 循環参照を検出
                return
            
            processing.add(comp_id)
            
            # このコンポーネントへの入力配線を探す
            for wire in self.wires.values():
                if wire.to_comp == comp_id:
                    visit(wire.from_comp)
            
            processing.remove(comp_id)
            visited.add(comp_id)
            order.append(comp_id)
        
        # 全てのコンポーネントを訪問
        for comp_id in self.components:
            visit(comp_id)
        
        # シミュレーション履歴を初期化
        total_steps = max(1, int(steps))
        if step_by_step or total_steps > 1:
            self.simulation_history = []
            self.current_step = 0

        # 出力記録を初期化
        for comp in self.components.values():
            if isinstance(comp, OutputDisplay):
                comp.clear_history()

        # 時間ステップを保存
        if time_step is not None:
            self.last_time_step = time_step
        
        # 時間ステップごとに計算
        for step_index in range(total_steps):
            # 入力パルスの更新
            for comp in self.components.values():
                if isinstance(comp, InputSource):
                    comp.update_pulse(step_index, time_step)

            # 計算順序に従って各コンポーネントを計算
            for comp_id in order:
                comp = self.components[comp_id]

                # 入力を収集
                for i, _ in enumerate(comp.inputs):
                    comp.inputs[i] = SignalState.UNDEFINED

                # 配線から入力を設定
                for wire in self.wires.values():
                    if wire.to_comp == comp_id:
                        from_comp = self.components[wire.from_comp]
                        if wire.to_input_index < len(comp.inputs):
                            comp.inputs[wire.to_input_index] = from_comp.output

                # 出力を計算
                comp.compute()

            # 出力記録
            for comp in self.components.values():
                if isinstance(comp, OutputDisplay):
                    comp.record_state()

            # 履歴に記録
            step_data = {comp_id: self.components[comp_id].output for comp_id in self.components}
            self.simulation_history.append(SimulationStep(step_index, step_data))
    
    def get_next_comp_id(self) -> str:
        """次のコンポーネントIDを生成"""
        comp_id = f"comp_{self.next_comp_id}"
        self.next_comp_id += 1
        return comp_id
    
    def get_next_wire_id(self) -> str:
        """次の配線IDを生成"""
        wire_id = f"wire_{self.next_wire_id}"
        self.next_wire_id += 1
        return wire_id
    
    def clear(self):
        """回路をクリア"""
        self.components.clear()
        self.wires.clear()
        self.simulation_history.clear()
        self.next_comp_id = 1
        self.next_wire_id = 1
        self.current_step = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "circuit_type": self.circuit_type.value,
            "components": [comp.to_dict() for comp in self.components.values()],
            "wires": [wire.to_dict() for wire in self.wires.values()]
        }
    
    def from_dict(self, data: Dict[str, Any]):
        """辞書から回路を復元"""
        self.clear()
        self.circuit_type = CircuitType(data.get("circuit_type", "logic"))
        
        # コンポーネントを復元
        for comp_data in data.get("components", []):
            comp = Component.from_dict(comp_data)
            self.components[comp.id] = comp
            
            # IDカウンターを更新
            if comp.id.startswith("comp_"):
                try:
                    num = int(comp.id.split("_")[1])
                    self.next_comp_id = max(self.next_comp_id, num + 1)
                except:
                    pass
        
        # 配線を復元
        for wire_data in data.get("wires", []):
            wire = Wire.from_dict(wire_data)
            self.wires[wire.wire_id] = wire
            
            # IDカウンターを更新
            if wire.wire_id.startswith("wire_"):
                try:
                    num = int(wire.wire_id.split("_")[1])
                    self.next_wire_id = max(self.next_wire_id, num + 1)
                except:
                    pass


# ========== 設定管理クラス ==========
class ConfigManager:
    """設定を管理するクラス"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = deepcopy(DEFAULT_CONFIG)
        self.load()
    
    def load(self):
        """設定を読み込む"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
                    # ショートカットキーのマージ
                    if "shortcuts" in loaded_config:
                        self.config["shortcuts"].update(loaded_config["shortcuts"])
        except Exception as e:
            print(f"設定ファイルの読み込みエラー: {e}")
    
    def save(self):
        """設定を保存する"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"設定ファイルの保存エラー: {e}")
    
    def get(self, key: str, default=None):
        """設定値を取得"""
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        """設定値を設定"""
        self.config[key] = value
        self.save()
    
    def get_shortcut(self, action: str) -> str:
        """ショートカットキーを取得"""
        shortcuts = self.config.get("shortcuts", DEFAULT_CONFIG["shortcuts"])
        return shortcuts.get(action, DEFAULT_CONFIG["shortcuts"].get(action, ""))
    
    def set_shortcut(self, action: str, key_sequence: str):
        """ショートカットキーを設定"""
        if "shortcuts" not in self.config:
            self.config["shortcuts"] = {}
        self.config["shortcuts"][action] = key_sequence
        self.save()


# ========== Undo/Redo マネージャー ==========
class CommandHistory:
    """Undo/Redo機能を管理するクラス"""
    
    def __init__(self, max_size: int = MAX_HISTORY):
        self.undo_stack: deque = deque(maxlen=max_size)
        self.redo_stack: deque = deque(maxlen=max_size)
    
    def execute(self, command: Command):
        """コマンドを実行"""
        command.execute()
        self.undo_stack.append(command)
        self.redo_stack.clear()  # redo スタックをクリア
    
    def undo(self) -> bool:
        """元に戻す"""
        if not self.undo_stack:
            return False
        command = self.undo_stack.pop()
        command.undo()
        self.redo_stack.append(command)
        return True
    
    def redo(self) -> bool:
        """やり直す"""
        if not self.redo_stack:
            return False
        command = self.redo_stack.pop()
        command.execute()
        self.undo_stack.append(command)
        return True
    
    def can_undo(self) -> bool:
        """元に戻せるか"""
        return len(self.undo_stack) > 0
    
    def can_redo(self) -> bool:
        """やり直せるか"""
        return len(self.redo_stack) > 0
    
    def clear(self):
        """履歴をクリア"""
        self.undo_stack.clear()
        self.redo_stack.clear()


# ========== シミュレーション表示パネル ==========
class SimulationPanel:
    """タブ内に埋め込まれるシミュレーション表示パネル"""
    
    def __init__(self, parent_frame, circuit: Circuit, callback_reset, callback_simulate):
        """
        Args:
            parent_frame: 親フレーム
            circuit: 回路オブジェクト
            callback_reset: リセット時のコールバック
            callback_simulate: シミュレーション実行時のコールバック
        """
        self.circuit = circuit
        self.callback_reset = callback_reset
        self.callback_simulate = callback_simulate
        
        # 親フレーム内にメインフレームを作成
        main_frame = ttk.Frame(parent_frame)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # シミュレーション設定フレーム（固定）
        config_frame = ttk.LabelFrame(main_frame, text="シミュレーション設定", padding=10)
        config_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        # 時間設定
        time_frame = ttk.Frame(config_frame)
        time_frame.pack(anchor="w", pady=5)
        ttk.Label(time_frame, text="実行時間:").pack(side=tk.LEFT)
        self.time_var = tk.DoubleVar(value=10.0)
        ttk.Entry(time_frame, textvariable=self.time_var, width=10).pack(side=tk.LEFT, padx=5)
        
        # 単位選択
        unit_frame = ttk.Frame(config_frame)
        unit_frame.pack(anchor="w", pady=5)
        ttk.Label(unit_frame, text="単位:").pack(side=tk.LEFT)
        self.unit_var = tk.StringVar(value="ms")
        ttk.Combobox(unit_frame, textvariable=self.unit_var, width=8,
                    values=[unit.symbol for unit in TimeUnit], state='readonly').pack(side=tk.LEFT, padx=5)
        
        # グラフ表示の最大時間設定
        display_time_frame = ttk.Frame(config_frame)
        display_time_frame.pack(anchor="w", pady=5)
        ttk.Label(display_time_frame, text="グラフ最大時間:").pack(side=tk.LEFT)
        self.display_time_var = tk.DoubleVar(value=10.0)
        ttk.Entry(display_time_frame, textvariable=self.display_time_var, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(display_time_frame, text="(式は実行時間と同じ単位)").pack(side=tk.LEFT, padx=5)
        
        # ボタン
        button_frame = ttk.Frame(config_frame)
        button_frame.pack(fill=tk.X, pady=10)
        ttk.Button(button_frame, text="▶ 実行", command=self.run_simulation).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="✕ リセット", command=self.reset_simulation).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="🔄 更新", command=self.refresh_waveform).pack(side=tk.LEFT, padx=2)
        
        # グラフフレーム（スクロール可能）
        graph_frame = ttk.LabelFrame(main_frame, text="波形グラフ", padding=5)
        graph_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # キャンバス + スクロールバーの構成
        canvas_container = ttk.Frame(graph_frame)
        canvas_container.pack(fill=tk.BOTH, expand=True)
        
        # Tkinterキャンバス（スクロール用）
        self.scroll_canvas = tk.Canvas(canvas_container, bg="white")
        self.scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # スクロールバー
        scrollbar = ttk.Scrollbar(canvas_container, orient=tk.VERTICAL, command=self.scroll_canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.scroll_canvas.configure(yscrollcommand=scrollbar.set)
        
        # スクロール可能なフレーム
        self.scrollable_frame = ttk.Frame(self.scroll_canvas)
        self.scroll_canvas_window = self.scroll_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # マウスホイールスクロール対応
        self.scroll_canvas.bind_all("<MouseWheel>", lambda e: self._on_mousewheel(e))
        
        # 初期状態では波形をプロット
        self.update_waveform()
    
    def run_simulation(self):
        """シミュレーションを実行"""
        try:
            time_val = self.time_var.get()
            unit_symbol = self.unit_var.get()
            time_unit = TimeUnit.from_symbol(unit_symbol)
            
            # コールバック実行
            self.callback_simulate(time_val, time_unit)
            
            # 波形更新
            self.update_waveform()
        except Exception as e:
            messagebox.showerror("エラー", f"シミュレーション実行エラー:\n{str(e)}")
    
    def reset_simulation(self):
        """シミュレーションをリセット"""
        try:
            self.callback_reset()
            self.update_waveform()
        except Exception as e:
            messagebox.showerror("エラー", f"リセットエラー:\n{str(e)}")
    
    def refresh_waveform(self):
        """波形を更新（ワークスペース変更時）"""
        try:
            self.update_waveform()
            messagebox.showinfo("情報", "波形グラフを更新しました")
        except Exception as e:
            messagebox.showerror("エラー", f"更新エラー:\n{str(e)}")
    
    def _on_mousewheel(self, event):
        """マウスホイールスクロール処理"""
        try:
            if self.scroll_canvas.winfo_containing(event.x_root, event.y_root) == self.scroll_canvas:
                self.scroll_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        except:
            pass
    
    def update_waveform(self):
        """波形グラフを更新（スクロール可能）"""
        # スクロール可能フレーム内の古いウィジェットをクリア
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # 入力と出力を分離
        inputs = [comp for comp in self.circuit.components.values() if isinstance(comp, InputSource)]
        outputs = [comp for comp in self.circuit.components.values() if isinstance(comp, OutputDisplay)]
        
        all_signals = inputs + outputs
        
        if not all_signals:
            ttk.Label(self.scrollable_frame, text="表示する信号がありません", font=("Arial", 10)).pack(pady=20)
            self._update_scroll_region()
            return
        
        # シミュレーション履歴が存在するか確認
        num_steps = len(self.circuit.simulation_history)
        
        # グラフ表示の最大時間を取得（ユーザー入力値）
        try:
            display_max_time_value = self.display_time_var.get()
            unit_symbol = self.unit_var.get()
            time_unit = TimeUnit.from_symbol(unit_symbol)
            # ユーザー入力値を秒に変換
            display_max_time_sec = display_max_time_value * time_unit.multiplier
        except:
            display_max_time_value = 10.0
            display_max_time_sec = 10.0
        
        if num_steps == 0:
            # テスト表示：シミュレーション前
            for comp in all_signals:
                fig = Figure(figsize=(5, 0.5), dpi=80)
                ax = fig.add_subplot(111)
                ax.text(0.5, 0.5, f"[{comp.get_type()}] {comp.name or comp.id}", 
                       ha='center', va='center', transform=ax.transAxes, fontsize=9)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis('off')
                
                # フレームに埋め込み
                frame = ttk.Frame(self.scrollable_frame)
                frame.pack(fill=tk.X, padx=5, pady=2)
                canvas = FigureCanvasTkAgg(fig, master=frame)
                canvas.get_tk_widget().pack(fill=tk.X)
        else:
            # 時間軸を生成(計算された最後の時間ステップを使用)
            time_step_sec = self.circuit.last_time_step
            time_values = [i * time_step_sec for i in range(num_steps)]
            
            for idx, comp in enumerate(all_signals):
                # 各信号を小さなグラフで表示
                fig = Figure(figsize=(5, 0.6), dpi=80)
                ax = fig.add_subplot(111)
                
                if isinstance(comp, InputSource):
                    # 入力信号
                    signal_values = []
                    for step in self.circuit.simulation_history:
                        state = step.component_states.get(comp.id, SignalState.UNDEFINED)
                        signal_values.append(1 if state == SignalState.HIGH else (0 if state == SignalState.LOW else None))
                    
                    ax.step(time_values, signal_values, where='post', linewidth=1.5, color='blue')
                else:
                    # 出力信号
                    signal_values = []
                    for state in comp.history:
                        signal_values.append(1 if state == SignalState.HIGH else (0 if state == SignalState.LOW else None))
                    
                    time_vals_out = time_values[:len(signal_values)]
                    ax.step(time_vals_out, signal_values, where='post', linewidth=1.5, color='orange')
                
                # グラフ設定
                ax.set_ylabel(comp.name or comp.id, fontsize=8)
                ax.set_ylim(-0.2, 1.2)
                ax.set_yticks([0, 1])
                ax.set_yticklabels(['0', '1'], fontsize=7)
                ax.set_xlim(0, display_max_time_sec)
                ax.grid(True, alpha=0.2)
                ax.tick_params(labelsize=7)
                
                # 最後のグラフに時間軸ラベルを表示
                if idx == len(all_signals) - 1:
                    ax.set_xlabel(f"時間 ({unit_symbol})", fontsize=8)
                
                # フレームに埋め込み
                frame = ttk.Frame(self.scrollable_frame)
                frame.pack(fill=tk.X, padx=5, pady=2)
                canvas = FigureCanvasTkAgg(fig, master=frame)
                canvas.get_tk_widget().pack(fill=tk.X)
        
        # スクロール領域を更新
        self._update_scroll_region()
    
    def _update_scroll_region(self):
        """スクロール領域のサイズを更新"""
        self.scrollable_frame.update_idletasks()
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))


# ========== 波形表示ダイアログ ==========
class WaveformDialog:
    """入出力信号の波形を表示するダイアログ"""
    
    def __init__(self, parent, circuit: Circuit, time_step: float, total_time: float, time_unit: TimeUnit):
        """
        Args:
            parent: 親ウィンドウ
            circuit: 回路オブジェクト
            time_step: 1ステップあたりの時間（秒単位）
            total_time: 総シミュレーション時間（time_unit単位）
            time_unit: 表示時間の単位
        """
        self.window = tk.Toplevel(parent)
        self.window.title("波形表示")
        self.window.geometry("1000x700")
        
        self.circuit = circuit
        self.time_step = time_step
        self.total_time = total_time
        self.time_unit = time_unit
        
        self.create_widgets()
    
    def create_widgets(self):
        """ウィジェットを作成"""
        # コントロールフレーム
        control_frame = ttk.Frame(self.window)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Label(control_frame, text="波形表示設定").pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="更新", command=self.update_plot).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_frame, text="閉じる", command=self.window.destroy).pack(side=tk.RIGHT, padx=5)
        
        # matplotlibグラフ
        self.fig = Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.window)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 初期プロット
        self.update_plot()
    
    def update_plot(self):
        """プロットを更新"""
        self.fig.clear()
        
        # 入力と出力を分離
        inputs = [comp for comp in self.circuit.components.values() if isinstance(comp, InputSource)]
        outputs = [comp for comp in self.circuit.components.values() if isinstance(comp, OutputDisplay)]
        
        if not inputs and not outputs:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "表示する信号がありません", ha='center', va='center', transform=ax.transAxes)
            self.canvas.draw()
            return
        
        # サブプロットの数を決定
        num_plots = len(inputs) + len(outputs)
        if num_plots == 0:
            return
        
        # 時間軸を生成
        num_steps = len(self.circuit.simulation_history)
        if num_steps == 0:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "シミュレーション履歴がありません", ha='center', va='center', transform=ax.transAxes)
            self.canvas.draw()
            return
        
        time_values = [i * self.time_step / self.time_unit.multiplier for i in range(num_steps)]
        
        plot_idx = 1
        
        # 入力信号をプロット
        for input_comp in inputs:
            ax = self.fig.add_subplot(num_plots, 1, plot_idx)
            
            # 履歴から信号値を取得
            signal_values = []
            for step in self.circuit.simulation_history:
                state = step.component_states.get(input_comp.id, SignalState.UNDEFINED)
                if state == SignalState.HIGH:
                    signal_values.append(1)
                elif state == SignalState.LOW:
                    signal_values.append(0)
                else:
                    signal_values.append(None)
            
            # 階段状の波形を描画
            ax.step(time_values, signal_values, where='post', linewidth=2, label=input_comp.name or input_comp.id)
            ax.set_ylabel('信号')
            ax.set_ylim(-0.2, 1.2)
            ax.set_yticks([0, 1])
            ax.set_yticklabels(['LOW', 'HIGH'])
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right')
            
            if plot_idx < num_plots:
                ax.set_xticklabels([])
            
            plot_idx += 1
        
        # 出力信号をプロット
        for output_comp in outputs:
            ax = self.fig.add_subplot(num_plots, 1, plot_idx)
            
            # 出力履歴から信号値を取得
            signal_values = []
            for state in output_comp.history:
                if state == SignalState.HIGH:
                    signal_values.append(1)
                elif state == SignalState.LOW:
                    signal_values.append(0)
                else:
                    signal_values.append(None)
            
            # 時間軸を調整（出力履歴の長さに合わせる）
            time_values_out = time_values[:len(signal_values)]
            
            # 階段状の波形を描画
            ax.step(time_values_out, signal_values, where='post', linewidth=2, color='orange', label=output_comp.name or output_comp.id)
            ax.set_ylabel('信号')
            ax.set_ylim(-0.2, 1.2)
            ax.set_yticks([0, 1])
            ax.set_yticklabels(['LOW', 'HIGH'])
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right')
            
            if plot_idx < num_plots:
                ax.set_xticklabels([])
            
            plot_idx += 1
        
        # 最後のプロットにのみX軸ラベルを追加
        ax.set_xlabel(f'時間 ({self.time_unit.symbol})')
        
        self.fig.tight_layout()
        self.canvas.draw()


# ========== メインGUIアプリケーション ==========
class CircuitSimulatorGUI:
    """回路シミュレータのGUIクラス"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Circuit Simulator - 論理回路シミュレータ")
        self.root.geometry("2000x1000")
        
        # 設定マネージャー
        self.config_manager = ConfigManager()
        
        # コマンド履歴 (Undo/Redo)
        self.command_history = CommandHistory()
        
        # 複数の回路を管理 (タブベース)
        self.circuits: Dict[str, Circuit] = {}
        self.current_circuit_tab = None
        self.tab_metadata_dict = {}  # {tab_id: tab_metadata}
        
        # GUI状態
        self.selected_gate_type = None
        self.selected_component = None
        self.dragging_component = None
        self.drag_offset = (0, 0)
        self.wiring_mode = False
        self.wire_start_comp = None
        self.wire_start_pin = None
        self.temp_wire_line = None
        self.wire_drag_mode = False  # D&Dでの配線モード
        self.panning = False  # カメラパンモード
        self.pan_start_x = 0
        self.pan_start_y = 0
        
        # ズーム状態
        self.zoom_level = DEFAULT_ZOOM
        
        # ステップ実行状態
        self.step_mode = False
        self.current_step = 0
        self.step_mode_steps = 20
        self.pulse_steps = 20
        
        # シミュレーション設定
        self.sim_total_time = 10.0  # 総シミュレーション時間（時間単位での値）
        self.sim_time_unit = TimeUnit.MILLISECONDS  # シミュレーション時間の単位
        self.sim_time_step = 0.1  # 1ステップあたりの時間（sim_time_unit単位）
        
        # キャンバス参照
        self.canvas = None
        self.canvas_items = {}  # comp_id -> canvas_item_id
        self.wire_items = {}    # wire_id -> canvas_item_id
        
        # UIの構築
        self.build_ui()
        
        # ウィンドウを閉じる時のイベント
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 新規回路を作成
        self.new_tab()
    
    def build_ui(self):
        """UIを構築"""
        # メニューバー
        self.create_menu()
        
        # メインフレーム
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左側: ツールパレット
        tool_frame = ttk.LabelFrame(main_frame, text="ツール", width=200)
        tool_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        tool_frame.pack_propagate(False)
        
        self.create_tool_palette(tool_frame)
        
        # 右側: メインコンテンツ
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # ノートブック (タブ管理)
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
        # コントロールパネル
        control_frame = ttk.Frame(right_frame)
        control_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        
        self.create_control_panel(control_frame)
    
    def create_menu(self):
        """メニューバーを作成"""
        menubar = Menu(self.root)
        self.root.config(menu=menubar)
        
        # ファイルメニュー
        file_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="ファイル", menu=file_menu)
        file_menu.add_command(label="新規", command=self.new_circuit)
        file_menu.add_command(label="新しいタブ", command=self.new_tab)
        file_menu.add_command(label="開く...", command=self.open_circuit)
        file_menu.add_command(label="保存", command=self.save_circuit)
        file_menu.add_command(label="名前を付けて保存...", command=self.save_circuit_as)
        file_menu.add_separator()
        file_menu.add_command(label="画像としてエクスポート...", command=self.export_as_image)
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=self.on_closing)
        
        # 編集メニュー
        edit_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="編集", menu=edit_menu)
        edit_menu.add_command(label="元に戻す", command=self.undo)
        edit_menu.add_command(label="やり直す", command=self.redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="クリア", command=self.clear_canvas)
        edit_menu.add_command(label="自動整列", command=self.auto_arrange)
        
        # ビューメニュー
        view_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="ビュー", menu=view_menu)
        view_menu.add_command(label="ズームイン", command=self.zoom_in)
        view_menu.add_command(label="ズームアウト", command=self.zoom_out)
        view_menu.add_command(label="100%にリセット", command=self.reset_zoom)
        view_menu.add_separator()
        view_menu.add_checkbutton(
            label="グリッド表示",
            command=self.toggle_grid,
            variable=tk.BooleanVar(value=self.config_manager.get("grid_enabled", True))
        )
        
        # シミュレーションメニュー
        sim_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="シミュレーション", menu=sim_menu)
        sim_menu.add_command(label="実行", command=self.run_simulation)
        sim_menu.add_command(label="ステップ実行", command=self.toggle_step_mode)
        sim_menu.add_command(label="次のステップ", command=self.next_step)
        sim_menu.add_command(label="リセット", command=self.reset_simulation)
        sim_menu.add_separator()
        sim_menu.add_command(label="波形表示", command=self.show_waveform)
        sim_menu.add_command(label="履歴表示", command=self.show_history)
        sim_menu.add_command(label="出力記録表示", command=self.show_output_records)
        sim_menu.add_separator()
        sim_menu.add_command(label="シミュレーション設定...", command=self.open_simulation_settings)
        sim_menu.add_command(label="パルス実行設定...", command=self.open_pulse_settings)
        
        # 設定メニュー
        settings_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="設定", menu=settings_menu)
        settings_menu.add_command(label="ショートカットキー設定...", command=self.open_shortcut_settings)
        settings_menu.add_separator()
        settings_menu.add_command(label="その他の設定...", command=self.open_settings)
        
        # ヘルプメニュー
        help_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="ヘルプ", menu=help_menu)
        help_menu.add_command(label="使い方", command=self.show_help)
        help_menu.add_command(label="バージョン情報", command=self.show_about)
        
        # ショートカットキーの登録
        self.register_shortcuts()
    
    def register_shortcuts(self):
        """ショートカットキーを登録"""
        self.root.bind(self.config_manager.get_shortcut("undo"), lambda e: self.undo())
        self.root.bind(self.config_manager.get_shortcut("redo"), lambda e: self.redo())
        self.root.bind(self.config_manager.get_shortcut("new"), lambda e: self.new_circuit())
        self.root.bind(self.config_manager.get_shortcut("open"), lambda e: self.open_circuit())
        self.root.bind(self.config_manager.get_shortcut("save"), lambda e: self.save_circuit())
        self.root.bind(self.config_manager.get_shortcut("zoom_in"), lambda e: self.zoom_in())
        self.root.bind(self.config_manager.get_shortcut("zoom_out"), lambda e: self.zoom_out())
        self.root.bind(self.config_manager.get_shortcut("delete"), lambda e: self.delete_selected())
        
        # モード切り替えのショートカット
        self.root.bind("<Control-w>", lambda e: self.switch_to_wire_mode())
        self.root.bind("<Escape>", lambda e: self.switch_to_move_mode())
    
    def create_tool_palette(self, parent):
        """ツールパレットを作成"""
        # タイトル
        ttk.Label(parent, text="論理ゲート", font=("Arial", 10, "bold")).pack(pady=5)
        
        # ゲートボタン
        gates = [
            ("AND", "AND"),
            ("OR", "OR"),
            ("NOT", "NOT"),
            ("NAND", "NAND"),
            ("NOR", "NOR"),
            ("XOR", "XOR"),
            ("XNOR", "XNOR"),
        ]
        
        for gate_name, gate_label in gates:
            btn = ttk.Button(
                parent,
                text=gate_label,
                command=lambda g=gate_name: self.select_gate(g)
            )
            btn.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 入出力
        ttk.Label(parent, text="入出力", font=("Arial", 10, "bold")).pack(pady=5)
        
        ttk.Button(
            parent,
            text="入力",
            command=lambda: self.select_gate("INPUT")
        ).pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(
            parent,
            text="出力",
            command=lambda: self.select_gate("OUTPUT")
        ).pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # ツール
        ttk.Label(parent, text="ツール", font=("Arial", 10, "bold")).pack(pady=5)
        
        # モード選択（ラジオボタン）
        self.tool_mode_var = tk.StringVar(value="move")
        
        ttk.Radiobutton(
            parent,
            text="移動モード (ESC)",
            variable=self.tool_mode_var,
            value="move",
            command=self.on_mode_change
        ).pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Radiobutton(
            parent,
            text="配線モード (Ctrl+W)",
            variable=self.tool_mode_var,
            value="wire",
            command=self.on_mode_change
        ).pack(fill=tk.X, padx=5, pady=2)
        
        # 選択中のゲート表示
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Label(parent, text="選択中:", font=("Arial", 9)).pack()
        self.selected_gate_label = ttk.Label(parent, text="移動モード", font=("Arial", 9, "bold"))
        self.selected_gate_label.pack()
        
        # ズームレベル表示
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Label(parent, text="ズーム:", font=("Arial", 9)).pack()
        self.zoom_level_label = ttk.Label(parent, text="100%", font=("Arial", 9, "bold"))
        self.zoom_level_label.pack()
    
    def create_control_panel(self, parent):
        """コントロールパネルを作成"""
        ttk.Button(parent, text="シミュレーション実行", command=self.run_simulation).pack(side=tk.LEFT, padx=5)
        ttk.Button(parent, text="リセット", command=self.reset_simulation).pack(side=tk.LEFT, padx=5)
        ttk.Button(parent, text="ステップ実行", command=self.toggle_step_mode).pack(side=tk.LEFT, padx=5)
        ttk.Button(parent, text="次へ", command=self.next_step).pack(side=tk.LEFT, padx=5)
        ttk.Button(parent, text="履歴表示", command=self.show_history).pack(side=tk.LEFT, padx=5)
        ttk.Button(parent, text="クリア", command=self.clear_canvas).pack(side=tk.LEFT, padx=5)
        
        # ステータスラベル
        self.status_label = ttk.Label(parent, text="準備完了", relief=tk.SUNKEN)
        self.status_label.pack(side=tk.RIGHT, padx=5)
    
    def new_tab(self):
        """新しいタブを作成"""
        tab_index = len(self.circuits)
        tab_id = f"circuit_{tab_index}"
        self.circuits[tab_id] = Circuit(CircuitType.LOGIC)
        
        # タブフレームを作成
        tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(tab_frame, text=f"回路 {tab_index + 1}")
        
        # 上部: コントロールボタンフレーム
        control_button_frame = ttk.Frame(tab_frame)
        control_button_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)
        
        ttk.Button(
            control_button_frame,
            text="📊 シミュレーションを開く",
            command=lambda: self.toggle_simulation_panel(tab_id)
        ).pack(side=tk.LEFT, padx=5)
        
        # 中部: PanedWindow（キャンバス + シミュレーションパネル）
        paned_window = ttk.PanedWindow(tab_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        # キャンバスフレーム
        canvas_frame = ttk.Frame(paned_window)
        paned_window.add(canvas_frame, weight=3)
        
        # キャンバス
        canvas = tk.Canvas(
            canvas_frame,
            bg="white",
            width=self.config_manager.get("canvas_width", CANVAS_WIDTH),
            height=self.config_manager.get("canvas_height", CANVAS_HEIGHT)
        )
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # スクロールバー
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        h_scrollbar = ttk.Scrollbar(tab_frame, orient=tk.HORIZONTAL, command=canvas.xview)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        canvas.configure(
            yscrollcommand=v_scrollbar.set,
            xscrollcommand=h_scrollbar.set,
            scrollregion=(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
        )
        
        # キャンバスイベント
        canvas.bind("<Button-1>", self.on_canvas_click)
        canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        canvas.bind("<B1-Motion>", self.on_canvas_drag)
        canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        canvas.bind("<Button-3>", self.on_canvas_right_click)
        canvas.bind("<Motion>", self.on_canvas_motion)
        canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        canvas.bind("<Button-4>", self.on_mouse_wheel)  # Linux
        canvas.bind("<Button-5>", self.on_mouse_wheel)  # Linux
        
        # シミュレーションパネルを作成（初期状態では追加しない）
        sim_panel_frame = ttk.Frame(paned_window)
        
        def callback_reset():
            """シミュレーションリセットコールバック"""
            circuit = self.circuits[tab_id]
            for comp in circuit.components.values():
                if isinstance(comp, InputSource):
                    comp.set_state(SignalState.LOW)
                comp.output = SignalState.UNDEFINED
            for comp in circuit.components.values():
                if isinstance(comp, OutputDisplay):
                    comp.clear_history()
            circuit.simulation_history.clear()
        
        def callback_simulate(time_val, time_unit):
            """シミュレーション実行コールバック"""
            circuit = self.circuits[tab_id]
            
            # デバッグ: circuit.components を詳しくダンプ
            print("\n=== circuit.components の内容 ===")
            for comp_id, comp in circuit.components.items():
                if isinstance(comp, InputSource):
                    print(f"{comp_id} -> {comp.id}: {comp.name}, pulse_period={comp.pulse_period}{comp.pulse_period_unit.symbol}, ref_id={id(comp)}")
            
            # ステップ数を計算
            steps = max(1, int(time_val / self.sim_time_step))
            time_step_sec = self.sim_time_step * time_unit.multiplier
            
            circuit.simulate(steps=steps, time_step=time_step_sec)
            self.update_status(f"シミュレーション完了: {time_val}{time_unit.symbol}")
        
        sim_panel = SimulationPanel(sim_panel_frame, self.circuits[tab_id], callback_reset, callback_simulate)
        sim_panel_frame.sim_panel = sim_panel  # 参照を保持
        
        # タブメタデータを保存
        self.tab_metadata_dict[tab_id] = {
            "canvas": canvas,
            "canvas_items": {},
            "wire_items": {},
            "v_scrollbar": v_scrollbar,
            "h_scrollbar": h_scrollbar,
            "paned_window": paned_window,
            "sim_panel_frame": sim_panel_frame,
            "sim_panel_visible": False
        }
        
        # グリッドを描画
        if self.config_manager.get("grid_enabled", True):
            self.draw_grid(canvas)
        
        # 現在のタブを選択
        self.notebook.select(len(self.notebook.tabs()) - 1)
        self.current_circuit_tab = tab_id
        self.canvas = canvas
        self.canvas_items = self.tab_metadata_dict[tab_id]["canvas_items"]
        self.wire_items = self.tab_metadata_dict[tab_id]["wire_items"]
        self.command_history.clear()
        
        self.update_status(f"新しいタブ '{self.notebook.tab(self.notebook.select(), 'text')}' を作成しました")
    
    def toggle_simulation_panel(self, tab_id: str):
        """シミュレーションパネルの表示/非表示を切り替え"""
        if tab_id not in self.tab_metadata_dict:
            return
        
        metadata = self.tab_metadata_dict[tab_id]
        paned_window = metadata["paned_window"]
        sim_panel_frame = metadata["sim_panel_frame"]
        
        # 現在の状態を反転
        is_visible = metadata["sim_panel_visible"]
        
        # パネルの表示/非表示を切り替え
        if is_visible:
            # 表示中 → 非表示
            try:
                paned_window.forget(sim_panel_frame)
                metadata["sim_panel_visible"] = False
                self.update_status("シミュレーションパネルを閉じました")
            except Exception as e:
                print(f"パネル非表示エラー: {e}")
        else:
            # 非表示 → 表示
            try:
                paned_window.add(sim_panel_frame, weight=1)
                metadata["sim_panel_visible"] = True
                # パネルの波形を更新
                if hasattr(sim_panel_frame, 'sim_panel'):
                    sim_panel_frame.sim_panel.update_waveform()
                self.update_status("シミュレーションパネルを開きました")
            except Exception as e:
                print(f"パネル表示エラー: {e}")
    
    def on_tab_changed(self, event):
        """タブが変更された時"""
        tab_index = self.notebook.index(self.notebook.select())
        tab_id = f"circuit_{tab_index}"
        
        if tab_id in self.circuits:
            self.current_circuit_tab = tab_id
            metadata = self.tab_metadata_dict[tab_id]
            self.canvas = metadata["canvas"]
            self.canvas_items = metadata["canvas_items"]
            self.wire_items = metadata["wire_items"]
            self.update_status(f"タブを切り替えました")
    
    def draw_grid(self, canvas):
        """グリッドを描画"""
        for x in range(0, CANVAS_WIDTH, GRID_SIZE):
            canvas.create_line(x, 0, x, CANVAS_HEIGHT, fill="lightgray", tags="grid")
        for y in range(0, CANVAS_HEIGHT, GRID_SIZE):
            canvas.create_line(0, y, CANVAS_WIDTH, y, fill="lightgray", tags="grid")
        
        # グリッドを背面に
        canvas.tag_lower("grid")
    
    def toggle_grid(self):
        """グリッド表示を切り替え"""
        if self.canvas.find_withtag("grid"):
            self.canvas.delete("grid")
            self.config_manager.set("grid_enabled", False)
        else:
            self.draw_grid(self.canvas)
            self.config_manager.set("grid_enabled", True)
    
    def select_gate(self, gate_type: str):
        """ゲートを選択"""
        self.selected_gate_type = gate_type
        self.selected_gate_label.config(text=gate_type)
        self.tool_mode_var.set("")
        self.wiring_mode = False
        self.update_status(f"{gate_type}ゲートを選択しました。キャンバスをクリックして配置してください。")
    
    def on_mode_change(self):
        """モード変更時の処理"""
        mode = self.tool_mode_var.get()
        self.selected_gate_type = None
        
        if mode == "wire":
            self.wiring_mode = True
            self.selected_gate_label.config(text="配線モード")
            self.update_status("配線モード: 出力ピンをクリックして、次に入力ピンをクリックしてください。")
        else:  # move
            self.wiring_mode = False
            self.selected_gate_label.config(text="移動モード")
            self.update_status("移動モード: コンポーネントをドラッグして移動できます。")
        
        # 配線開始状態をクリア
        self.wire_start_comp = None
        self.wire_start_pin = None
        if self.temp_wire_line:
            self.canvas.delete(self.temp_wire_line)
            self.temp_wire_line = None
    
    def toggle_wire_mode(self):
        """配線モードをトグル (旧関数 - 互換性のため保持)"""
        if self.tool_mode_var.get() == "wire":
            self.tool_mode_var.set("move")
        else:
            self.tool_mode_var.set("wire")
        self.on_mode_change()
    
    def switch_to_wire_mode(self):
        """配線モードに切り替え"""
        self.tool_mode_var.set("wire")
        self.on_mode_change()
    
    def switch_to_move_mode(self):
        """移動モードに切り替え"""
        self.tool_mode_var.set("move")
        self.on_mode_change()
    
    def snap_to_grid(self, x: float, y: float) -> Tuple[float, float]:
        """座標をグリッドにスナップ"""
        if self.config_manager.get("snap_to_grid", True):
            x = round(x / GRID_SIZE) * GRID_SIZE
            y = round(y / GRID_SIZE) * GRID_SIZE
        return x, y
    
    def zoom_in(self):
        """ズームイン"""
        if self.zoom_level < MAX_ZOOM:
            old_zoom = self.zoom_level
            self.zoom_level = min(self.zoom_level + ZOOM_STEP, MAX_ZOOM)
            self.apply_zoom(old_zoom, self.zoom_level)
            self.update_zoom_display()
    
    def zoom_out(self):
        """ズームアウト"""
        if self.zoom_level > MIN_ZOOM:
            old_zoom = self.zoom_level
            self.zoom_level = max(self.zoom_level - ZOOM_STEP, MIN_ZOOM)
            self.apply_zoom(old_zoom, self.zoom_level)
            self.update_zoom_display()
    
    def reset_zoom(self):
        """ズームをリセット"""
        old_zoom = self.zoom_level
        self.zoom_level = DEFAULT_ZOOM
        self.apply_zoom(old_zoom, self.zoom_level)
        self.update_zoom_display()
    
    def apply_zoom(self, old_zoom: float, new_zoom: float):
        """ズームを適用"""
        if old_zoom == new_zoom:
            return
        
        # スケール倍率を計算
        scale_factor = new_zoom / old_zoom
        
        # キャンバス中心を取得
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        center_x = canvas_width / 2
        center_y = canvas_height / 2
        
        # すべてのアイテムをスケーリング
        self.canvas.scale("all", center_x, center_y, scale_factor, scale_factor)
        
        # コンポーネントの座標も更新
        circuit = self.circuits.get(self.current_circuit_tab)
        if circuit:
            for comp in circuit.components.values():
                # 中心からの相対位置を計算してスケーリング
                dx = comp.x - center_x
                dy = comp.y - center_y
                comp.x = center_x + dx * scale_factor
                comp.y = center_y + dy * scale_factor
    
    def on_mouse_wheel(self, event):
        """マウスホイール操作 (ズーム)"""
        if event.num == 5 or event.delta < 0:
            self.zoom_out()
        elif event.num == 4 or event.delta > 0:
            self.zoom_in()
    
    def update_zoom_display(self):
        """ズーム表示を更新"""
        percentage = int(self.zoom_level * 100)
        self.zoom_level_label.config(text=f"{percentage}%")
        self.update_status(f"ズームレベル: {percentage}%")
    
    def on_canvas_click(self, event):
        """キャンバスクリック時の処理"""
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        
        if self.wiring_mode:
            self.handle_wiring_click(x, y)
        elif self.selected_gate_type:
            self.place_component(x, y)
        elif self.tool_mode_var.get() == "move":
            # 移動モード: コンポーネントをクリックしたか確認
            comp_clicked = self.handle_component_selection(x, y)
            
            if not comp_clicked:
                # コンポーネントがない場合、カメラパン開始
                self.panning = True
                self.pan_start_x = event.x
                self.pan_start_y = event.y
                self.canvas.config(cursor="fleur")  # カーソル変更
        else:
            # コンポーネントをクリックしたか確認（ピンより優先）
            comp_clicked = self.handle_component_selection(x, y)
            
            if not comp_clicked:
                # コンポーネントがない場合、ピンをチェック
                pin_info = self.find_pin_at_position(x, y)
                if pin_info and pin_info[1] == "output":
                    self.wire_start_comp = pin_info[0]
                    self.wire_drag_mode = True
                    self.update_status("出力ピンから配線をドラッグしてください。")
                else:
                    # 何もない場所をクリック → カメラパン開始
                    self.panning = True
                    self.pan_start_x = event.x
                    self.pan_start_y = event.y
                    self.canvas.config(cursor="fleur")  # カーソル変更
    
    def place_component(self, x: float, y: float):
        """コンポーネントを配置"""
        x, y = self.snap_to_grid(x, y)
        
        circuit = self.circuits[self.current_circuit_tab]
        comp_id = circuit.get_next_comp_id()
        
        # コンポーネントを作成
        gate_classes = {
            "AND": ANDGate,
            "OR": ORGate,
            "NOT": NOTGate,
            "NAND": NANDGate,
            "NOR": NORGate,
            "XOR": XORGate,
            "XNOR": XNORGate,
            "INPUT": InputSource,
            "OUTPUT": OutputDisplay
        }
        
        if self.selected_gate_type in gate_classes:
            comp = gate_classes[self.selected_gate_type](x, y, comp_id)
            
            # コマンド履歴に追加
            cmd = AddComponentCommand(circuit, comp)
            self.command_history.execute(cmd)
            
            self.draw_component(comp)
            self.update_status(f"{self.selected_gate_type}ゲートを配置しました (ID: {comp_id})")
    
    def draw_component(self, comp: Component):
        """コンポーネントを描画"""
        x, y = comp.x, comp.y
        gate_type = comp.get_type()
        
        # ゲートの矩形
        rect = self.canvas.create_rectangle(
            x - GATE_WIDTH/2, y - GATE_HEIGHT/2,
            x + GATE_WIDTH/2, y + GATE_HEIGHT/2,
            fill="lightblue", outline="black", width=2,
            tags=(f"comp_{comp.id}", "component")
        )
        
        # ゲート名のテキスト
        self.canvas.create_text(
            x, y - 8,
            text=gate_type,
            font=("Arial", 11, "bold"),
            tags=(f"comp_{comp.id}", "component", "component_label")
        )

        # コンポーネント名のテキスト
        self.canvas.create_text(
            x, y + 12,
            text=comp.name,
            font=("Arial", 9),
            tags=(f"comp_{comp.id}", "component", "component_name")
        )
        
        # 入力ピン
        num_inputs = len(comp.inputs)
        for i in range(num_inputs):
            pin_y = y - GATE_HEIGHT/2 + GATE_HEIGHT * (i + 1) / (num_inputs + 1)
            pin = self.canvas.create_oval(
                x - GATE_WIDTH/2 - PIN_RADIUS, pin_y - PIN_RADIUS,
                x - GATE_WIDTH/2 + PIN_RADIUS, pin_y + PIN_RADIUS,
                fill="green", outline="darkgreen",
                tags=(f"comp_{comp.id}", "input_pin", f"pin_{comp.id}_in_{i}")
            )
        
        # 出力ピン
        pin = self.canvas.create_oval(
            x + GATE_WIDTH/2 - PIN_RADIUS, y - PIN_RADIUS,
            x + GATE_WIDTH/2 + PIN_RADIUS, y + PIN_RADIUS,
            fill="red", outline="darkred",
            tags=(f"comp_{comp.id}", "output_pin", f"pin_{comp.id}_out")
        )
        
        self.canvas_items[comp.id] = rect
    
    def handle_component_selection(self, x: float, y: float) -> bool:
        """コンポーネントの選択処理
        
        Returns:
            bool: コンポーネントが選択された場合True
        """
        comp = self.find_component_at_position(x, y)
        if not comp:
            return False

        # 入力ソースの場合はトグル
        if isinstance(comp, InputSource):
            comp.toggle()
            self.update_component_display(comp)
            self.update_status(f"入力を切り替えました: {comp.output.name}")
            return True

        # 通常のコンポーネントはドラッグ準備
        self.selected_component = comp
        self.dragging_component = comp
        self.drag_offset = (comp.x - x, comp.y - y)
        self.update_status(f"コンポーネント選択: {comp.get_type()} ({comp.name})")
        return True

    def find_component_at_position(self, x: float, y: float) -> Optional[Component]:
        """クリック位置からコンポーネントを検索"""
        circuit = self.circuits.get(self.current_circuit_tab)
        if not circuit:
            return None

        for comp in circuit.components.values():
            if (comp.x - GATE_WIDTH/2 <= x <= comp.x + GATE_WIDTH/2 and
                comp.y - GATE_HEIGHT/2 <= y <= comp.y + GATE_HEIGHT/2):
                return comp

        return None

    def on_canvas_double_click(self, event):
        """ダブルクリックでプロパティを開く"""
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        comp = self.find_component_at_position(x, y)
        if comp:
            self.open_component_properties(comp)

    def open_component_properties(self, comp: Component):
        """コンポーネントのプロパティ編集"""
        prop_window = tk.Toplevel(self.root)
        prop_window.title("コンポーネント設定")
        prop_window.geometry("480x520")
        prop_window.transient(self.root)

        # 基本情報
        ttk.Label(prop_window, text=f"タイプ: {comp.get_type()}").pack(anchor="w", padx=10, pady=5)
        ttk.Label(prop_window, text=f"ID: {comp.id}").pack(anchor="w", padx=10, pady=5)

        ttk.Label(prop_window, text="名称:").pack(anchor="w", padx=10, pady=5)
        name_entry = ttk.Entry(prop_window, width=40)
        name_entry.insert(0, comp.name)
        name_entry.pack(anchor="w", padx=10, pady=5)

        # パルス設定（InputSourceの場合）
        pulse_enabled_var = tk.BooleanVar(value=False)
        period_var = tk.DoubleVar(value=1.0)
        period_unit_var = tk.StringVar(value="ms")
        duty_var = tk.DoubleVar(value=50.0)
        phase_var = tk.DoubleVar(value=0.0)
        phase_unit_var = tk.StringVar(value="ms")

        if isinstance(comp, InputSource):
            period_var.set(comp.pulse_period)
            period_unit_var.set(comp.pulse_period_unit.symbol)
            duty_var.set(comp.pulse_duty_cycle * 100.0)
            phase_var.set(comp.pulse_phase)
            phase_unit_var.set(comp.pulse_phase_unit.symbol)

            ttk.Separator(prop_window, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=10)
            ttk.Label(prop_window, text="パルス設定", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=5)
            
            # 周期設定
            period_frame = ttk.Frame(prop_window)
            period_frame.pack(anchor="w", padx=10, pady=5)
            ttk.Label(period_frame, text="周期:").pack(side=tk.LEFT)
            ttk.Entry(period_frame, textvariable=period_var, width=12).pack(side=tk.LEFT, padx=5)
            ttk.Combobox(period_frame, textvariable=period_unit_var, width=8,
                        values=[unit.symbol for unit in TimeUnit], state='readonly').pack(side=tk.LEFT)
            
            # デューティ比
            duty_frame = ttk.Frame(prop_window)
            duty_frame.pack(anchor="w", padx=10, pady=5)
            ttk.Label(duty_frame, text="デューティ比:").pack(side=tk.LEFT)
            ttk.Entry(duty_frame, textvariable=duty_var, width=12).pack(side=tk.LEFT, padx=5)
            ttk.Label(duty_frame, text="%").pack(side=tk.LEFT)
            
            # 位相設定
            phase_frame = ttk.Frame(prop_window)
            phase_frame.pack(anchor="w", padx=10, pady=5)
            ttk.Label(phase_frame, text="位相:").pack(side=tk.LEFT)
            ttk.Entry(phase_frame, textvariable=phase_var, width=12).pack(side=tk.LEFT, padx=5)
            ttk.Combobox(phase_frame, textvariable=phase_unit_var, width=8,
                        values=[unit.symbol for unit in TimeUnit], state='readonly').pack(side=tk.LEFT)
            
            # 説明
            info_text = "※時間ベースのパルス設定です。\nシミュレーション設定の時間単位と合わせて使用してください。"
            ttk.Label(prop_window, text=info_text, foreground="gray", font=("Arial", 8)).pack(anchor="w", padx=10, pady=5)

        # 出力表示（OutputDisplayの場合）
        if isinstance(comp, OutputDisplay):
            ttk.Separator(prop_window, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=10)
            ttk.Label(prop_window, text=f"記録数: {len(comp.history)}").pack(anchor="w", padx=10, pady=5)
            ttk.Button(prop_window, text="出力記録を表示", 
                      command=lambda: self.show_output_records(target_id=comp.id)).pack(anchor="w", padx=10, pady=5)
            ttk.Button(prop_window, text="出力記録をクリア", 
                      command=comp.clear_history).pack(anchor="w", padx=10, pady=5)

        def save_properties():
            comp.name = name_entry.get().strip() or comp.id
            if isinstance(comp, InputSource):
                comp.pulse_enabled = True  # パルスは常に有効
                comp.pulse_period = max(0.001, float(period_var.get()))
                comp.pulse_period_unit = TimeUnit.from_symbol(period_unit_var.get())
                comp.pulse_duty_cycle = max(0.01, min(1.0, float(duty_var.get()) / 100.0))
                comp.pulse_phase = float(phase_var.get())
                comp.pulse_phase_unit = TimeUnit.from_symbol(phase_unit_var.get())
                # デバッグ: 保存内容をログに出力
                print(f"save_properties(): ID={comp.id}, 周期={comp.pulse_period}{comp.pulse_period_unit.symbol}, デューティ比={comp.pulse_duty_cycle}")
            self.redraw_canvas()
            self.update_status(f"{comp.get_type()} の設定を更新しました")
            prop_window.destroy()

        # ボタン
        button_frame = ttk.Frame(prop_window)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="保存", command=save_properties).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="キャンセル", command=prop_window.destroy).pack(side=tk.LEFT, padx=5)
    
    def on_canvas_drag(self, event):
        """キャンバスドラッグ時の処理"""
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        
        if self.panning:
            # カメラをパン（移動）- マウスの動きと同じだけキャンバスを移動
            dx = event.x - self.pan_start_x
            dy = event.y - self.pan_start_y
            
            # すべてのアイテムを移動
            self.canvas.move("all", dx, dy)
            
            # コンポーネントの座標も更新
            circuit = self.circuits.get(self.current_circuit_tab)
            if circuit:
                for comp in circuit.components.values():
                    comp.x += dx
                    comp.y += dy
            
            self.pan_start_x = event.x
            self.pan_start_y = event.y
        
        elif self.dragging_component:
            # コンポーネントを移動
            new_x = x + self.drag_offset[0]
            new_y = y + self.drag_offset[1]
            new_x, new_y = self.snap_to_grid(new_x, new_y)
            
            dx = new_x - self.dragging_component.x
            dy = new_y - self.dragging_component.y
            
            # 実際に移動した場合のみ更新
            if dx != 0 or dy != 0:
                self.dragging_component.x = new_x
                self.dragging_component.y = new_y
                
                # キャンバス上のアイテムを移動
                for item in self.canvas.find_withtag(f"comp_{self.dragging_component.id}"):
                    self.canvas.move(item, dx, dy)
                
                # 関連する配線を更新
                self.update_wires_for_component(self.dragging_component.id)
        
        elif (self.wiring_mode or self.wire_drag_mode) and self.wire_start_comp:
            # 仮の配線を表示
            if self.temp_wire_line:
                self.canvas.delete(self.temp_wire_line)
            
            circuit = self.circuits[self.current_circuit_tab]
            start_comp = circuit.components[self.wire_start_comp]
            start_x = start_comp.x + GATE_WIDTH/2
            start_y = start_comp.y
            
            self.temp_wire_line = self.canvas.create_line(
                start_x, start_y, x, y,
                fill="blue", width=2, dash=(4, 4)
            )
    
    def on_canvas_release(self, event):
        """キャンバスリリース時の処理"""
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        
        # カメラパンモードを終了
        if self.panning:
            self.panning = False
            self.canvas.config(cursor="")
        
        # D&D配線モードの場合
        if self.wire_drag_mode and self.wire_start_comp:
            pin_info = self.find_pin_at_position(x, y)
            if pin_info and pin_info[1] == "input":
                # 入力ピンで離した場合は配線を作成
                comp_id, pin_type, pin_index = pin_info
                circuit = self.circuits[self.current_circuit_tab]
                
                wire_id = circuit.get_next_wire_id()
                wire = Wire(
                    wire_id=wire_id,
                    from_comp=self.wire_start_comp,
                    to_comp=comp_id,
                    to_input_index=pin_index
                )
                
                cmd = AddWireCommand(circuit, wire)
                self.command_history.execute(cmd)
                self.draw_wire(wire)
                self.update_status(f"配線を作成しました (ID: {wire_id})")
            
            # D&D配線モードをリセット
            self.wire_drag_mode = False
            self.wire_start_comp = None
            if self.temp_wire_line:
                self.canvas.delete(self.temp_wire_line)
                self.temp_wire_line = None
        
        self.dragging_component = None
    
    def on_canvas_right_click(self, event):
        """右クリック時の処理 (コンポーネント削除)"""
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        item = self.canvas.find_closest(x, y)[0]
        tags = self.canvas.gettags(item)
        
        for tag in tags:
            if tag.startswith("comp_"):
                comp_id = tag.split("_")[1]
                circuit = self.circuits[self.current_circuit_tab]
                if comp_id in circuit.components:
                    # 確認ダイアログ
                    result = messagebox.askyesno(
                        "削除確認",
                        f"コンポーネント ({circuit.components[comp_id].get_type()}) を削除しますか?"
                    )
                    if result:
                        self.remove_component(comp_id)
                break
    
    def on_canvas_motion(self, event):
        """マウス移動時の処理"""
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        
        # カーソルの下にあるアイテムを取得
        item = self.canvas.find_closest(x, y)[0]
        tags = self.canvas.gettags(item)
        
        # ツールチップ的な情報表示
        if "component" in tags:
            for tag in tags:
                if tag.startswith("comp_"):
                    comp_id = tag.split("_")[1]
                    circuit = self.circuits[self.current_circuit_tab]
                    if comp_id in circuit.components:
                        comp = circuit.components[comp_id]
                        name_text = comp.name if comp.name else comp.id
                        output_text = comp.output.name if comp.output else "N/A"
                        self.status_label.config(
                            text=f"{comp.get_type()} ({name_text}) | 出力: {output_text}"
                        )
    
    def find_pin_at_position(self, x: float, y: float, search_radius: float = 30.0) -> Optional[Tuple[str, str, int]]:
        """指定位置にあるピンを検索
        
        Returns:
            (comp_id, pin_type, pin_index) or None
            pin_type: "output" or "input"
            pin_index: 入力ピンのインデックス (出力ピンの場合は0)
        """
        circuit = self.circuits.get(self.current_circuit_tab)
        if not circuit:
            return None
        
        # 最も近いピンを記録
        closest_pin = None
        closest_distance = search_radius
        
        for comp_id, comp in circuit.components.items():
            # 出力ピンをチェック
            output_pin_x = comp.x + GATE_WIDTH/2
            output_pin_y = comp.y
            distance = math.sqrt((x - output_pin_x)**2 + (y - output_pin_y)**2)
            if distance < closest_distance:
                closest_distance = distance
                closest_pin = (comp_id, "output", 0)
            
            # 入力ピンをチェック
            num_inputs = len(comp.inputs)
            for i in range(num_inputs):
                pin_y = comp.y - GATE_HEIGHT/2 + GATE_HEIGHT * (i + 1) / (num_inputs + 1)
                input_pin_x = comp.x - GATE_WIDTH/2
                input_pin_y = pin_y
                distance = math.sqrt((x - input_pin_x)**2 + (y - input_pin_y)**2)
                if distance < closest_distance:
                    closest_distance = distance
                    closest_pin = (comp_id, "input", i)
        
        return closest_pin
    
    def handle_wiring_click(self, x: float, y: float):
        """配線クリック時の処理"""
        pin_info = self.find_pin_at_position(x, y)
        
        if pin_info is None:
            # ピンが見つからない場合は配線開始をキャンセル
            if self.wire_start_comp:
                self.wire_start_comp = None
                self.wire_start_pin = None
                if self.temp_wire_line:
                    self.canvas.delete(self.temp_wire_line)
                    self.temp_wire_line = None
                self.update_status("配線をキャンセルしました。")
            return
        
        comp_id, pin_type, pin_index = pin_info
        
        if pin_type == "output":
            # 出力ピンをクリック
            self.wire_start_comp = comp_id
            self.wire_start_pin = "out"
            self.update_status("出力ピンを選択しました。次に入力ピンをクリックしてください。")
        
        elif pin_type == "input" and self.wire_start_comp:
            # 入力ピンをクリック (配線完成)
            circuit = self.circuits[self.current_circuit_tab]
            
            # 配線を作成
            wire_id = circuit.get_next_wire_id()
            wire = Wire(
                wire_id=wire_id,
                from_comp=self.wire_start_comp,
                to_comp=comp_id,
                to_input_index=pin_index
            )
            
            # コマンド履歴に追加
            cmd = AddWireCommand(circuit, wire)
            self.command_history.execute(cmd)
            
            self.draw_wire(wire)
            
            # リセット
            self.wire_start_comp = None
            self.wire_start_pin = None
            if self.temp_wire_line:
                self.canvas.delete(self.temp_wire_line)
                self.temp_wire_line = None
            
            self.update_status(f"配線を作成しました (ID: {wire_id})")
    
    def draw_wire(self, wire: Wire):
        """配線を描画"""
        circuit = self.circuits[self.current_circuit_tab]
        from_comp = circuit.components[wire.from_comp]
        to_comp = circuit.components[wire.to_comp]
        
        # 出力ピンの位置
        start_x = from_comp.x + GATE_WIDTH/2
        start_y = from_comp.y
        
        # 入力ピンの位置
        num_inputs = len(to_comp.inputs)
        pin_y = to_comp.y - GATE_HEIGHT/2 + GATE_HEIGHT * (wire.to_input_index + 1) / (num_inputs + 1)
        end_x = to_comp.x - GATE_WIDTH/2
        end_y = pin_y
        
        # 配線を描画 (シンプルな直線)
        line = self.canvas.create_line(
            start_x, start_y, end_x, end_y,
            fill="black", width=2,
            tags=(f"wire_{wire.wire_id}", "wire")
        )
        
        self.wire_items[wire.wire_id] = line
    
    def update_wires_for_component(self, comp_id: str):
        """コンポーネントに関連する配線を更新"""
        circuit = self.circuits[self.current_circuit_tab]
        for wire_id, wire in circuit.wires.items():
            if wire.from_comp == comp_id or wire.to_comp == comp_id:
                # 配線を再描画
                if wire_id in self.wire_items:
                    self.canvas.delete(self.wire_items[wire_id])
                self.draw_wire(wire)
    
    def remove_component(self, comp_id: str):
        """コンポーネントを削除"""
        circuit = self.circuits[self.current_circuit_tab]
        
        # キャンバスから削除
        for item in self.canvas.find_withtag(f"comp_{comp_id}"):
            self.canvas.delete(item)
        
        # 関連する配線を削除
        wires_to_remove = [
            wire_id for wire_id, wire in circuit.wires.items()
            if wire.from_comp == comp_id or wire.to_comp == comp_id
        ]
        for wire_id in wires_to_remove:
            if wire_id in self.wire_items:
                self.canvas.delete(self.wire_items[wire_id])
                del self.wire_items[wire_id]
        
        # コマンド履歴に追加
        cmd = RemoveComponentCommand(circuit, comp_id)
        self.command_history.execute(cmd)
        
        if comp_id in self.canvas_items:
            del self.canvas_items[comp_id]
        
        self.update_status(f"コンポーネントを削除しました (ID: {comp_id})")
    
    def delete_selected(self):
        """選択中のコンポーネントを削除"""
        if self.selected_component:
            self.remove_component(self.selected_component.id)
            self.selected_component = None
    
    def update_component_display(self, comp: Component):
        """コンポーネントの表示を更新"""
        # 入力ソースの色を変更
        if isinstance(comp, InputSource):
            for item in self.canvas.find_withtag(f"comp_{comp.id}"):
                if self.canvas.type(item) == "rectangle":
                    color = "yellow" if comp.output == SignalState.HIGH else "lightblue"
                    self.canvas.itemconfig(item, fill=color)
    
    def toggle_step_mode(self):
        """ステップ実行モードをトグル"""
        self.step_mode = not self.step_mode
        if self.step_mode:
            circuit = self.circuits[self.current_circuit_tab]
            circuit.simulate(step_by_step=True, steps=self.step_mode_steps)
            self.current_step = 0
            self.apply_simulation_step(0)
            self.update_status("ステップ実行モード: 有効")
        else:
            self.update_status("ステップ実行モード: 無効")
    
    def next_step(self):
        """次のステップに進む"""
        if not self.step_mode:
            messagebox.showwarning("警告", "まずステップ実行モードを有効にしてください")
            return
        
        circuit = self.circuits[self.current_circuit_tab]
        if self.current_step < len(circuit.simulation_history) - 1:
            self.current_step += 1
            self.apply_simulation_step(self.current_step)
            self.update_status(f"ステップ: {self.current_step + 1}")
        else:
            messagebox.showinfo("情報", "最後のステップです")
    
    def run_simulation(self):
        """シミュレーションを実行"""
        try:
            circuit = self.circuits[self.current_circuit_tab]
            pulse_inputs = [c for c in circuit.components.values() if isinstance(c, InputSource) and c.pulse_enabled]
            
            # パルス入力がある場合は時間ベースのシミュレーション
            if pulse_inputs:
                # ステップ数を計算
                steps = int(self.sim_total_time / self.sim_time_step)
                time_step_sec = self.sim_time_step * self.sim_time_unit.multiplier
                circuit.simulate(steps=steps, time_step=time_step_sec)
            else:
                # パルスなしの場合は単一ステップ
                circuit.simulate(steps=1)
            
            self.update_all_displays()
            self.update_status("シミュレーションを実行しました。")
            messagebox.showinfo("シミュレーション完了", "シミュレーションが正常に完了しました。")
        except Exception as e:
            messagebox.showerror("シミュレーションエラー", f"エラーが発生しました:\n{str(e)}")

    def apply_simulation_step(self, step_index: int):
        """履歴の指定ステップを画面に反映"""
        circuit = self.circuits[self.current_circuit_tab]
        if not circuit.simulation_history:
            return
        step = circuit.simulation_history[max(0, min(step_index, len(circuit.simulation_history) - 1))]
        for comp_id, state in step.component_states.items():
            if comp_id in circuit.components:
                circuit.components[comp_id].output = state
        self.update_all_displays()

    def open_pulse_settings(self):
        """パルス実行設定を開く（後方互換性）"""
        value = simpledialog.askinteger("パルス実行設定", "パルス実行のステップ数を入力してください (1-1000)",
                                        initialvalue=self.pulse_steps, minvalue=1, maxvalue=1000)
        if value:
            self.pulse_steps = value
            self.update_status(f"パルス実行ステップ数: {self.pulse_steps}")
    
    def open_simulation_settings(self):
        """シミュレーション設定ダイアログを開く"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("シミュレーション設定")
        settings_window.geometry("500x300")
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        # メインフレーム
        main_frame = ttk.Frame(settings_window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 総シミュレーション時間
        ttk.Label(main_frame, text="総シミュレーション時間:").grid(row=0, column=0, sticky=tk.W, pady=5)
        total_time_var = tk.DoubleVar(value=self.sim_total_time)
        ttk.Entry(main_frame, textvariable=total_time_var, width=15).grid(row=0, column=1, pady=5)
        
        # 時間単位
        ttk.Label(main_frame, text="時間単位:").grid(row=0, column=2, sticky=tk.W, padx=(10, 0), pady=5)
        time_unit_var = tk.StringVar(value=self.sim_time_unit.symbol)
        time_unit_combo = ttk.Combobox(main_frame, textvariable=time_unit_var, width=10, 
                                       values=[unit.symbol for unit in TimeUnit], state='readonly')
        time_unit_combo.grid(row=0, column=3, pady=5)
        
        # 時間ステップ
        ttk.Label(main_frame, text="時間ステップ（1ステップあたり）:").grid(row=1, column=0, sticky=tk.W, pady=5)
        time_step_var = tk.DoubleVar(value=self.sim_time_step)
        ttk.Entry(main_frame, textvariable=time_step_var, width=15).grid(row=1, column=1, pady=5)
        ttk.Label(main_frame, text="(同じ単位)").grid(row=1, column=2, columnspan=2, sticky=tk.W, padx=(10, 0), pady=5)
        
        # 計算されるステップ数の表示
        steps_label = ttk.Label(main_frame, text="")
        steps_label.grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=5)
        
        def update_steps_label(*args):
            try:
                total = total_time_var.get()
                step = time_step_var.get()
                if step > 0:
                    steps = int(total / step)
                    steps_label.config(text=f"計算ステップ数: {steps}")
                else:
                    steps_label.config(text="計算ステップ数: N/A")
            except:
                steps_label.config(text="計算ステップ数: N/A")
        
        total_time_var.trace('w', update_steps_label)
        time_step_var.trace('w', update_steps_label)
        update_steps_label()
        
        # 説明
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).grid(row=3, column=0, columnspan=4, sticky="ew", pady=10)
        info_text = (
            "シミュレーションの総時間と時間解像度を設定します。\n"
            "例: 10msを0.1msステップでシミュレーションすると100ステップになります。"
        )
        ttk.Label(main_frame, text=info_text, wraplength=450, justify=tk.LEFT).grid(
            row=4, column=0, columnspan=4, sticky=tk.W, pady=5
        )
        
        # ボタン
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=4, pady=20)
        
        def apply_settings():
            try:
                self.sim_total_time = total_time_var.get()
                self.sim_time_unit = TimeUnit.from_symbol(time_unit_var.get())
                self.sim_time_step = time_step_var.get()
                self.update_status("シミュレーション設定を更新しました。")
                settings_window.destroy()
            except Exception as e:
                messagebox.showerror("エラー", f"設定の適用に失敗しました:\n{str(e)}")
        
        ttk.Button(button_frame, text="適用", command=apply_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="キャンセル", command=settings_window.destroy).pack(side=tk.LEFT, padx=5)
    
    def show_waveform(self):
        """波形表示ダイアログを開く"""
        circuit = self.circuits[self.current_circuit_tab]
        if not circuit.simulation_history:
            messagebox.showinfo("情報", "シミュレーションを先に実行してください。")
            return
        
        # 時間ステップを計算
        time_step_sec = self.sim_time_step * self.sim_time_unit.multiplier
        
        # 波形ダイアログを表示
        WaveformDialog(self.root, circuit, time_step_sec, self.sim_total_time, self.sim_time_unit)
    
    def reset_simulation(self):
        """シミュレーションをリセット"""
        circuit = self.circuits[self.current_circuit_tab]
        for comp in circuit.components.values():
            if isinstance(comp, InputSource):
                comp.set_state(SignalState.LOW)
            comp.output = SignalState.UNDEFINED
        
        self.step_mode = False
        self.current_step = 0
        self.update_all_displays()
        self.update_status("シミュレーションをリセットしました。")
    
    def update_all_displays(self):
        """全てのコンポーネントの表示を更新"""
        circuit = self.circuits[self.current_circuit_tab]
        for comp in circuit.components.values():
            self.update_component_display(comp)
            
            # 出力ディスプレイの表示を更新
            if isinstance(comp, OutputDisplay):
                for item in self.canvas.find_withtag(f"comp_{comp.id}"):
                    if self.canvas.type(item) == "rectangle":
                        if comp.output == SignalState.HIGH:
                            self.canvas.itemconfig(item, fill="lime")
                        elif comp.output == SignalState.LOW:
                            self.canvas.itemconfig(item, fill="gray")
                        else:
                            self.canvas.itemconfig(item, fill="lightblue")
        
        # 配線の色も更新
        for wire_id, wire in circuit.wires.items():
            from_comp = circuit.components[wire.from_comp]
            if wire_id in self.wire_items:
                if from_comp.output == SignalState.HIGH:
                    self.canvas.itemconfig(self.wire_items[wire_id], fill="red", width=3)
                elif from_comp.output == SignalState.LOW:
                    self.canvas.itemconfig(self.wire_items[wire_id], fill="blue", width=2)
                else:
                    self.canvas.itemconfig(self.wire_items[wire_id], fill="gray", width=2)
    
    def show_history(self):
        """シミュレーション履歴を表示"""
        circuit = self.circuits[self.current_circuit_tab]
        if not circuit.simulation_history:
            messagebox.showinfo("情報", "シミュレーション履歴がありません")
            return
        
        # 履歴表示ウィンドウを作成
        history_window = tk.Toplevel(self.root)
        history_window.title("シミュレーション履歴")
        history_window.geometry("600x400")
        
        # ツリービューで表示
        tree = ttk.Treeview(history_window, columns=("コンポーネント", "状態"), height=15)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        tree.column("#0", width=100, heading="ステップ")
        tree.column("コンポーネント", width=200)
        tree.column("状態", width=100)
        
        tree.heading("#0", text="ステップ")
        tree.heading("コンポーネント", text="コンポーネント")
        tree.heading("状態", text="状態")
        
        # 履歴データを追加
        for step in circuit.simulation_history:
            step_text = f"Step {step.step_number}"
            parent = tree.insert("", "end", text=step_text)
            for comp_id, state in step.component_states.items():
                state_text = state.name if state else "UNDEFINED"
                comp = circuit.components.get(comp_id)
                name_text = comp.name if comp else comp_id
                tree.insert(parent, "end", text=comp_id, values=(f"{name_text}", state_text))

    def show_output_records(self, target_id: Optional[str] = None):
        """出力記録を表示"""
        circuit = self.circuits[self.current_circuit_tab]
        outputs = [c for c in circuit.components.values() if isinstance(c, OutputDisplay)]
        if target_id:
            outputs = [c for c in outputs if c.id == target_id]
        
        if not outputs:
            messagebox.showinfo("情報", "出力記録がありません")
            return

        record_window = tk.Toplevel(self.root)
        record_window.title("出力記録")
        record_window.geometry("700x400")

        tree = ttk.Treeview(record_window, columns=("出力", "状態"), height=18)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        tree.column("#0", width=80, heading="ステップ")
        tree.column("出力", width=250)
        tree.column("状態", width=120)
        tree.heading("#0", text="ステップ")
        tree.heading("出力", text="出力")
        tree.heading("状態", text="状態")

        max_len = max((len(o.history) for o in outputs), default=0)
        for step_index in range(max_len):
            step_label = f"Step {step_index}"
            parent = tree.insert("", "end", text=step_label)
            for output in outputs:
                state = output.history[step_index] if step_index < len(output.history) else SignalState.UNDEFINED
                tree.insert(parent, "end", text=output.id, values=(output.name, state.name))
    
    def clear_canvas(self):
        """キャンバスをクリア"""
        result = messagebox.askyesno("確認", "キャンバスをクリアしますか?")
        if result:
            circuit = self.circuits[self.current_circuit_tab]
            self.canvas.delete("component")
            self.canvas.delete("wire")
            circuit.clear()
            self.canvas_items.clear()
            self.wire_items.clear()
            self.command_history.clear()
            self.update_status("キャンバスをクリアしました。")
    
    def auto_arrange(self):
        """自動整列 - 配線を考慮した階層構造で配置"""
        circuit = self.circuits[self.current_circuit_tab]
        if not circuit.components:
            messagebox.showinfo("情報", "配置するコンポーネントがありません。")
            return
        
        # トポロジカルソートで階層を決定
        layers = {}
        in_degree = {comp_id: 0 for comp_id in circuit.components}
        
        # 各コンポーネントへの入力数をカウント
        for wire in circuit.wires.values():
            if wire.to_comp in in_degree:
                in_degree[wire.to_comp] += 1
        
        # 入力がないノード（入力ソース等）から開始
        queue = [comp_id for comp_id, degree in in_degree.items() if degree == 0]
        layer_num = 0
        
        while queue:
            current_layer = queue[:]
            layers[layer_num] = current_layer
            queue = []
            
            for comp_id in current_layer:
                # このコンポーネントから出ている配線を追跡
                for wire in circuit.wires.values():
                    if wire.from_comp == comp_id:
                        if wire.to_comp in in_degree:
                            in_degree[wire.to_comp] -= 1
                            if in_degree[wire.to_comp] == 0 and wire.to_comp not in queue:
                                queue.append(wire.to_comp)
            
            layer_num += 1
        
        # 循環参照がある場合、残りを最終層に配置
        remaining = [comp_id for comp_id, degree in in_degree.items() if degree > 0]
        if remaining:
            layers[layer_num] = remaining
        
        # 各層のコンポーネントを配置
        x_offset = 100
        y_offset = 100
        layer_spacing = GATE_WIDTH + 120  # 層間の間隔
        vertical_spacing = GATE_HEIGHT + 60  # 垂直間隔
        
        for layer_idx in sorted(layers.keys()):
            layer_comps = layers[layer_idx]
            x = x_offset + layer_idx * layer_spacing
            
            for i, comp_id in enumerate(layer_comps):
                if comp_id in circuit.components:
                    comp = circuit.components[comp_id]
                    y = y_offset + i * vertical_spacing
                    
                    # コンポーネントを移動
                    dx = x - comp.x
                    dy = y - comp.y
                    comp.x = x
                    comp.y = y
                    
                    # キャンバス上のアイテムを移動
                    for item in self.canvas.find_withtag(f"comp_{comp.id}"):
                        self.canvas.move(item, dx, dy)
        
        # 配線を更新
        for wire_id, wire in circuit.wires.items():
            if wire_id in self.wire_items:
                self.canvas.delete(self.wire_items[wire_id])
            self.draw_wire(wire)
        
        self.update_status("コンポーネントを配線考慮型で自動整列しました。")
    
    def undo(self):
        """元に戻す"""
        if self.command_history.undo():
            self.redraw_canvas()
            self.update_status("元に戻しました")
        else:
            messagebox.showinfo("情報", "元に戻すことはできません")
    
    def redo(self):
        """やり直す"""
        if self.command_history.redo():
            self.redraw_canvas()
            self.update_status("やり直しました")
        else:
            messagebox.showinfo("情報", "やり直すことはできません")
    
    def redraw_canvas(self):
        """キャンバスを再描画"""
        circuit = self.circuits[self.current_circuit_tab]
        
        # キャンバスを完全にクリア（ピン、配線、コンポーネント全て）
        self.canvas.delete("all")
        self.canvas_items.clear()
        self.wire_items.clear()
        
        # グリッドを再描画
        if self.config_manager.get("grid_enabled", True):
            self.draw_grid(self.canvas)
        
        # コンポーネントを再描画
        for comp in circuit.components.values():
            self.draw_component(comp)
        
        # 配線を再描画
        for wire in circuit.wires.values():
            self.draw_wire(wire)
        
        self.update_all_displays()
    
    def new_circuit(self):
        """新規回路を作成"""
        result = messagebox.askyesno("確認", "現在の回路を破棄して新規作成しますか?")
        if result:
            self.clear_canvas()
            self.config_manager.set("last_project", "")
            self.update_status("新規回路を作成しました。")
    
    def save_circuit(self):
        """回路を保存"""
        last_project = self.config_manager.get("last_project", "")
        if last_project and os.path.exists(last_project):
            self.save_to_file(last_project)
        else:
            self.save_circuit_as()
    
    def save_circuit_as(self):
        """名前を付けて保存"""
        project_dir = os.path.join(os.path.dirname(__file__), "project")
        os.makedirs(project_dir, exist_ok=True)
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=project_dir
        )
        
        if file_path:
            self.save_to_file(file_path)
    
    def save_to_file(self, file_path: str):
        """ファイルに保存"""
        try:
            circuit = self.circuits[self.current_circuit_tab]
            data = circuit.to_dict()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            self.config_manager.set("last_project", file_path)
            self.update_status(f"回路を保存しました: {os.path.basename(file_path)}")
            messagebox.showinfo("保存完了", "回路を保存しました。")
        except Exception as e:
            messagebox.showerror("保存エラー", f"保存中にエラーが発生しました:\n{str(e)}")
    
    def open_circuit(self):
        """回路を開く"""
        project_dir = os.path.join(os.path.dirname(__file__), "project")
        os.makedirs(project_dir, exist_ok=True)
        
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=project_dir
        )
        
        if file_path:
            self.load_from_file(file_path)
    
    def load_from_file(self, file_path: str):
        """ファイルから読み込み"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            circuit = self.circuits[self.current_circuit_tab]
            
            # キャンバスをクリア
            self.canvas.delete("component")
            self.canvas.delete("wire")
            self.canvas_items.clear()
            self.wire_items.clear()
            
            # 回路を復元
            circuit.from_dict(data)
            
            # コンポーネントを描画
            for comp in circuit.components.values():
                self.draw_component(comp)
            
            # 配線を描画
            for wire in circuit.wires.values():
                self.draw_wire(wire)
            
            self.config_manager.set("last_project", file_path)
            self.command_history.clear()
            self.update_status(f"回路を読み込みました: {os.path.basename(file_path)}")
            messagebox.showinfo("読み込み完了", "回路を読み込みました。")
        except Exception as e:
            messagebox.showerror("読み込みエラー", f"読み込み中にエラーが発生しました:\n{str(e)}")
    
    def export_as_image(self):
        """画像としてエクスポート"""
        try:
            from PIL import Image, ImageDraw
            import io
            
            # PostScriptとして出力
            ps = self.canvas.postscript(colormode='color')
            
            # 保存先を選択
            file_path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png"), ("All files", "*.*")]
            )
            
            if file_path:
                # PostScriptをPNGに変換 (Pillowを使用)
                img = Image.open(io.BytesIO(ps.encode('utf-8')))
                img.save(file_path)
                self.update_status(f"画像をエクスポートしました: {os.path.basename(file_path)}")
                messagebox.showinfo("エクスポート完了", "画像をエクスポートしました。")
        except ImportError:
            messagebox.showerror(
                "エラー",
                "画像エクスポートにはPillowライブラリが必要です。\n'pip install pillow'でインストールしてください。"
            )
        except Exception as e:
            messagebox.showerror("エクスポートエラー", f"エクスポート中にエラーが発生しました:\n{str(e)}")
    
    def open_shortcut_settings(self):
        """ショートカットキー設定ダイアログを開く"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("ショートカットキー設定")
        settings_window.geometry("500x600")
        
        # スクロール可能なフレーム
        canvas = tk.Canvas(settings_window)
        scrollbar = ttk.Scrollbar(settings_window, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # ショートカットキーフィールド
        shortcuts = self.config_manager.config.get("shortcuts", DEFAULT_CONFIG["shortcuts"])
        
        entries = {}
        for action, default_key in DEFAULT_CONFIG["shortcuts"].items():
            current_key = shortcuts.get(action, default_key)
            
            ttk.Label(scrollable_frame, text=f"{action}:", font=("Arial", 10)).pack(pady=5)
            entry = ttk.Entry(scrollable_frame, width=40)
            entry.insert(0, current_key)
            entry.pack(pady=5, padx=10)
            entries[action] = entry
        
        def save_shortcuts():
            for action, entry in entries.items():
                key_sequence = entry.get().strip()
                if key_sequence:
                    self.config_manager.set_shortcut(action, key_sequence)
            self.register_shortcuts()
            messagebox.showinfo("保存完了", "ショートカットキーを保存しました。")
            settings_window.destroy()
        
        # 保存ボタン
        ttk.Button(scrollable_frame, text="保存", command=save_shortcuts).pack(pady=10)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def open_settings(self):
        """設定ダイアログを開く"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("設定")
        settings_window.geometry("400x300")
        
        # グリッド設定
        ttk.Label(settings_window, text="グリッドサイズ:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        grid_size_var = tk.IntVar(value=GRID_SIZE)
        ttk.Spinbox(settings_window, from_=10, to=50, textvariable=grid_size_var).grid(row=0, column=1, padx=10, pady=5)
        
        # スナップ設定
        snap_var = tk.BooleanVar(value=self.config_manager.get("snap_to_grid", True))
        ttk.Checkbutton(settings_window, text="グリッドにスナップ", variable=snap_var).grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        
        # 自動保存設定
        auto_save_var = tk.BooleanVar(value=self.config_manager.get("auto_save", True))
        ttk.Checkbutton(settings_window, text="自動保存", variable=auto_save_var).grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="w")
        
        def save_settings():
            self.config_manager.set("snap_to_grid", snap_var.get())
            self.config_manager.set("auto_save", auto_save_var.get())
            messagebox.showinfo("設定保存", "設定を保存しました。")
            settings_window.destroy()
        
        ttk.Button(settings_window, text="保存", command=save_settings).grid(row=10, column=0, columnspan=2, pady=20)
    
    def show_help(self):
        """ヘルプを表示"""
        help_text = """
Circuit Simulator - 使い方

1. ゲート配置:
   - 左側のツールパレットからゲートを選択
   - キャンバスをクリックして配置

2. 配線:
   - 「配線モード」をチェック
   - 出力ピン(赤)をクリック
   - 入力ピン(緑)をクリックして接続

3. 入力設定:
   - 入力コンポーネント (INPUT) をクリックして切り替え

4. シミュレーション:
   - 「シミュレーション実行」ボタンをクリック

5. ステップ実行:
   - 「ステップ実行」ボタンをクリック
   - 「次へ」ボタンで1ステップ進める

6. 履歴表示:
   - 「履歴表示」ボタンをクリック
   - シミュレーション結果の各ステップを確認

7. Undo/Redo:
   - Ctrl+Z: 元に戻す
   - Ctrl+Y: やり直す

8. ズーム:
   - Ctrl+プラス: ズームイン
   - Ctrl+マイナス: ズームアウト
   - マウスホイール: ズーム操作

9. 保存/読み込み:
   - ファイルメニューから保存/開くを選択

10. その他:
    - 右クリック: コンポーネント削除
    - ドラッグ: コンポーネント移動
    - 複数タブ: 複数の回路を管理
        """
        messagebox.showinfo("使い方", help_text)
    
    def show_about(self):
        """バージョン情報を表示"""
        about_text = """
Circuit Simulator
バージョン 2.0.0

論理回路シミュレータ
(将来的に量子回路もサポート予定)

新機能:
- Undo/Redo 機能
- ズームイン・アウト
- 複数回路のタブ管理
- ステップ実行機能
- シミュレーション履歴表示
- ショートカットキーカスタマイズ

© 2026
        """
        messagebox.showinfo("バージョン情報", about_text)
    
    def update_status(self, message: str):
        """ステータスを更新"""
        self.status_label.config(text=message)
    
    def on_closing(self):
        """ウィンドウを閉じる時の処理"""
        circuit = self.circuits.get(self.current_circuit_tab)
        if circuit and self.config_manager.get("auto_save", True):
            last_project = self.config_manager.get("last_project", "")
            if last_project and circuit.components:
                result = messagebox.askyesnocancel("確認", "変更を保存しますか?")
                if result is True:
                    self.save_circuit()
                elif result is None:
                    return
        
        self.root.destroy()


# ========== メイン実行 ==========
def main():
    """メイン関数"""
    root = tk.Tk()
    app = CircuitSimulatorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
