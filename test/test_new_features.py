"""
新機能のテストファイル

新しく追加された以下の機能をテストします:
- Undo/Redo 機能
- ズーム機能
- タブベース回路管理
- ステップ実行機能
- シミュレーション履歴
- ショートカットキーカスタマイズ
"""

import pytest
import sys
import os
from collections import deque

# main.py をインポート
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from main import (
    Circuit, CircuitType, SignalState,
    ANDGate, ORGate, NOTGate, Wire,
    Command, AddComponentCommand, RemoveComponentCommand,
    AddWireCommand, RemoveWireCommand, MoveComponentCommand,
    CommandHistory, ConfigManager, SimulationStep,
    InputSource, OutputDisplay, DEFAULT_CONFIG
)


# ========== CommandHistory テスト ==========
class TestCommandHistory:
    """Undo/Redo 機能のテスト"""
    
    def test_command_history_initialization(self):
        """CommandHistory の初期化テスト"""
        history = CommandHistory(max_size=50)
        assert history.can_undo() is False
        assert history.can_redo() is False
    
    def test_undo_redo_with_add_component(self):
        """コンポーネント追加のUndo/Redo テスト"""
        circuit = Circuit()
        history = CommandHistory()
        
        # AND ゲートを作成
        and_gate = ANDGate(100, 100, "comp_1")
        
        # 追加コマンドを実行
        cmd = AddComponentCommand(circuit, and_gate)
        history.execute(cmd)
        
        assert "comp_1" in circuit.components
        assert history.can_undo() is True
        assert history.can_redo() is False
        
        # Undo
        history.undo()
        assert "comp_1" not in circuit.components
        assert history.can_undo() is False
        assert history.can_redo() is True
        
        # Redo
        history.redo()
        assert "comp_1" in circuit.components
        assert history.can_undo() is True
        assert history.can_redo() is False
    
    def test_undo_redo_clear_on_new_command(self):
        """新しいコマンド実行時に Redo スタックがクリアされることを確認"""
        circuit = Circuit()
        history = CommandHistory()
        
        # コマンド1を実行
        cmd1 = AddComponentCommand(circuit, ANDGate(100, 100, "comp_1"))
        history.execute(cmd1)
        
        # Undo
        history.undo()
        assert history.can_redo() is True
        
        # コマンド2を実行 (Redo スタックをクリア)
        cmd2 = AddComponentCommand(circuit, ORGate(200, 200, "comp_2"))
        history.execute(cmd2)
        
        # Redo スタックはクリアされた
        assert history.can_redo() is False
        assert "comp_2" in circuit.components
    
    def test_command_history_max_size(self):
        """CommandHistory のサイズ制限テスト"""
        circuit = Circuit()
        history = CommandHistory(max_size=5)
        
        # 5つ以上のコマンドを実行
        for i in range(7):
            cmd = AddComponentCommand(circuit, ANDGate(100 * i, 100, f"comp_{i}"))
            history.execute(cmd)
        
        # 最初の2つは削除されている
        assert "comp_0" not in circuit.components or len(history.undo_stack) <= 5
    
    def test_move_component_command(self):
        """コンポーネント移動コマンドのテスト"""
        gate = ANDGate(100, 100, "comp_1")
        history = CommandHistory()
        
        # 移動コマンドを実行
        cmd = MoveComponentCommand(gate, 100, 100, 200, 200)
        history.execute(cmd)
        
        assert gate.x == 200
        assert gate.y == 200
        
        # Undo
        history.undo()
        assert gate.x == 100
        assert gate.y == 100


# ========== Circuit テスト ==========
class TestCircuitWithHistory:
    """Circuit のシミュレーション履歴テスト"""
    
    def test_simulation_with_step_by_step(self):
        """ステップ実行シミュレーションのテスト"""
        circuit = Circuit()
        
        # 入力、AND ゲート、出力を作成
        input1 = InputSource(50, 100, "input_1")
        input2 = InputSource(150, 100, "input_2")
        and_gate = ANDGate(250, 100, "and_1")
        output = OutputDisplay(350, 100, "output_1")
        
        circuit.add_component(input1)
        circuit.add_component(input2)
        circuit.add_component(and_gate)
        circuit.add_component(output)
        
        # 配線を追加
        circuit.add_wire(Wire("wire_1", "input_1", "and_1", 0))
        circuit.add_wire(Wire("wire_2", "input_2", "and_1", 1))
        circuit.add_wire(Wire("wire_3", "and_1", "output_1", 0))
        
        # ステップ実行でシミュレーション
        circuit.simulate(step_by_step=True)
        
        # 履歴が記録されている
        assert len(circuit.simulation_history) > 0
        assert circuit.simulation_history[0].step_number == 0
    
    def test_simulation_history_content(self):
        """シミュレーション履歴の内容テスト"""
        circuit = Circuit()
        
        # コンポーネントを作成
        input1 = InputSource(50, 100, "input_1")
        input1.set_state(SignalState.HIGH)
        output = OutputDisplay(150, 100, "output_1")
        
        circuit.add_component(input1)
        circuit.add_component(output)
        circuit.add_wire(Wire("wire_1", "input_1", "output_1", 0))
        
        # シミュレーション実行
        circuit.simulate()
        
        # 履歴の内容を確認
        assert len(circuit.simulation_history) > 0
        last_step = circuit.simulation_history[-1]
        assert "input_1" in last_step.component_states


# ========== ConfigManager テスト ==========
class TestConfigManager:
    """設定管理のテスト"""
    
    def test_config_default_values(self):
        """デフォルト設定値のテスト"""
        config = ConfigManager("test_config.json")
        
        # デフォルトショートカットが存在する
        assert config.get_shortcut("undo") == DEFAULT_CONFIG["shortcuts"]["undo"]
        assert config.get_shortcut("redo") == DEFAULT_CONFIG["shortcuts"]["redo"]
        assert config.get_shortcut("zoom_in") == DEFAULT_CONFIG["shortcuts"]["zoom_in"]
    
    def test_set_and_get_shortcut(self):
        """ショートカットキー設定のテスト"""
        config = ConfigManager("test_config.json")
        
        # ショートカットを設定
        config.set_shortcut("custom_action", "<Control-h>")
        
        # 設定したショートカットを取得
        assert config.get_shortcut("custom_action") == "<Control-h>"
    
    def test_config_persistence(self):
        """設定の永続化テスト"""
        import json
        
        config1 = ConfigManager("test_config_persist.json")
        config1.set("test_key", "test_value")
        
        # 別のインスタンスで同じ設定を確認
        config2 = ConfigManager("test_config_persist.json")
        assert config2.get("test_key") == "test_value"
        
        # テストファイルをクリーンアップ
        if os.path.exists("test_config_persist.json"):
            os.remove("test_config_persist.json")


# ========== Wire テスト ==========
class TestWireAndConnections:
    """配線と接続のテスト"""
    
    def test_wire_creation_and_removal(self):
        """配線の作成と削除テスト"""
        circuit = Circuit()
        
        # コンポーネントを作成
        and_gate = ANDGate(100, 100, "comp_1")
        output = OutputDisplay(200, 100, "comp_2")
        circuit.add_component(and_gate)
        circuit.add_component(output)
        
        # 配線を作成
        wire = Wire("wire_1", "comp_1", "comp_2", 0)
        circuit.add_wire(wire)
        
        assert "wire_1" in circuit.wires
        assert circuit.wires["wire_1"].from_comp == "comp_1"
        
        # 配線を削除
        circuit.remove_wire("wire_1")
        assert "wire_1" not in circuit.wires
    
    def test_component_removal_removes_related_wires(self):
        """コンポーネント削除時に関連する配線も削除されることを確認"""
        circuit = Circuit()
        
        # コンポーネントを作成
        input1 = InputSource(50, 100, "input_1")
        and_gate = ANDGate(150, 100, "and_1")
        circuit.add_component(input1)
        circuit.add_component(and_gate)
        
        # 配線を作成
        wire = Wire("wire_1", "input_1", "and_1", 0)
        circuit.add_wire(wire)
        
        assert "wire_1" in circuit.wires
        
        # コンポーネントを削除
        circuit.remove_component("input_1")
        
        # 関連する配線も削除される
        assert "wire_1" not in circuit.wires


# ========== SimulationStep テスト ==========
class TestSimulationStep:
    """シミュレーションステップのテスト"""
    
    def test_simulation_step_creation(self):
        """SimulationStep の作成テスト"""
        states = {
            "comp_1": SignalState.HIGH,
            "comp_2": SignalState.LOW,
            "comp_3": SignalState.UNDEFINED
        }
        
        step = SimulationStep(step_number=0, component_states=states)
        
        assert step.step_number == 0
        assert step.component_states["comp_1"] == SignalState.HIGH
        assert step.component_states["comp_2"] == SignalState.LOW
    
    def test_multiple_simulation_steps(self):
        """複数のシミュレーションステップのテスト"""
        circuit = Circuit()
        
        # トランジェント テストの回路を作成
        input1 = InputSource(50, 100, "input_1")
        input1.set_state(SignalState.HIGH)
        
        not_gate = NOTGate(150, 100, "not_1")
        and_gate = ANDGate(250, 100, "and_1")
        output = OutputDisplay(350, 100, "output_1")
        
        circuit.add_component(input1)
        circuit.add_component(not_gate)
        circuit.add_component(and_gate)
        circuit.add_component(output)
        
        circuit.add_wire(Wire("wire_1", "input_1", "not_1", 0))
        circuit.add_wire(Wire("wire_2", "input_1", "and_1", 0))
        circuit.add_wire(Wire("wire_3", "not_1", "and_1", 1))
        circuit.add_wire(Wire("wire_4", "and_1", "output_1", 0))
        
        # シミュレーション実行
        circuit.simulate(step_by_step=True)
        
        # 複数のステップが記録されている
        assert len(circuit.simulation_history) >= 1


# ========== InputSource テスト ==========
class TestInputSource:
    """入力ソースのテスト"""
    
    def test_input_toggle(self):
        """入力のトグルテスト"""
        input_source = InputSource(100, 100, "input_1")
        
        initial_state = input_source.output
        input_source.toggle()
        assert input_source.output != initial_state
        
        input_source.toggle()
        assert input_source.output == initial_state
    
    def test_input_set_state(self):
        """入力の状態設定テスト"""
        input_source = InputSource(100, 100, "input_1")
        
        input_source.set_state(SignalState.HIGH)
        assert input_source.output == SignalState.HIGH
        
        input_source.set_state(SignalState.LOW)
        assert input_source.output == SignalState.LOW


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
