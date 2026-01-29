"""
Circuit Simulator - テストコード

このテストコードは、論理回路シミュレータの基本機能をテストします。
"""

import sys
import os

# main.pyをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    ANDGate, ORGate, NOTGate, NANDGate, NORGate, XORGate, XNORGate,
    InputSource, OutputDisplay, Circuit, Wire, SignalState
)


def test_and_gate():
    """ANDゲートのテスト"""
    print("Testing AND Gate...")
    gate = ANDGate(0, 0, "test_and")
    
    # テストケース1: 0 AND 0 = 0
    gate.inputs = [SignalState.LOW, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    # テストケース2: 0 AND 1 = 0
    gate.inputs = [SignalState.LOW, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    # テストケース3: 1 AND 0 = 0
    gate.inputs = [SignalState.HIGH, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    # テストケース4: 1 AND 1 = 1
    gate.inputs = [SignalState.HIGH, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    print("✓ AND Gate test passed")


def test_or_gate():
    """ORゲートのテスト"""
    print("Testing OR Gate...")
    gate = ORGate(0, 0, "test_or")
    
    # テストケース1: 0 OR 0 = 0
    gate.inputs = [SignalState.LOW, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    # テストケース2: 0 OR 1 = 1
    gate.inputs = [SignalState.LOW, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    # テストケース3: 1 OR 0 = 1
    gate.inputs = [SignalState.HIGH, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    # テストケース4: 1 OR 1 = 1
    gate.inputs = [SignalState.HIGH, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    print("✓ OR Gate test passed")


def test_not_gate():
    """NOTゲートのテスト"""
    print("Testing NOT Gate...")
    gate = NOTGate(0, 0, "test_not")
    
    # テストケース1: NOT 0 = 1
    gate.inputs = [SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    # テストケース2: NOT 1 = 0
    gate.inputs = [SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    print("✓ NOT Gate test passed")


def test_nand_gate():
    """NANDゲートのテスト"""
    print("Testing NAND Gate...")
    gate = NANDGate(0, 0, "test_nand")
    
    # テストケース1: 0 NAND 0 = 1
    gate.inputs = [SignalState.LOW, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    # テストケース2: 0 NAND 1 = 1
    gate.inputs = [SignalState.LOW, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    # テストケース3: 1 NAND 0 = 1
    gate.inputs = [SignalState.HIGH, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    # テストケース4: 1 NAND 1 = 0
    gate.inputs = [SignalState.HIGH, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    print("✓ NAND Gate test passed")


def test_nor_gate():
    """NORゲートのテスト"""
    print("Testing NOR Gate...")
    gate = NORGate(0, 0, "test_nor")
    
    # テストケース1: 0 NOR 0 = 1
    gate.inputs = [SignalState.LOW, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    # テストケース2: 0 NOR 1 = 0
    gate.inputs = [SignalState.LOW, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    # テストケース3: 1 NOR 0 = 0
    gate.inputs = [SignalState.HIGH, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    # テストケース4: 1 NOR 1 = 0
    gate.inputs = [SignalState.HIGH, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    print("✓ NOR Gate test passed")


def test_xor_gate():
    """XORゲートのテスト"""
    print("Testing XOR Gate...")
    gate = XORGate(0, 0, "test_xor")
    
    # テストケース1: 0 XOR 0 = 0
    gate.inputs = [SignalState.LOW, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    # テストケース2: 0 XOR 1 = 1
    gate.inputs = [SignalState.LOW, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    # テストケース3: 1 XOR 0 = 1
    gate.inputs = [SignalState.HIGH, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    # テストケース4: 1 XOR 1 = 0
    gate.inputs = [SignalState.HIGH, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    print("✓ XOR Gate test passed")


def test_xnor_gate():
    """XNORゲートのテスト"""
    print("Testing XNOR Gate...")
    gate = XNORGate(0, 0, "test_xnor")
    
    # テストケース1: 0 XNOR 0 = 1
    gate.inputs = [SignalState.LOW, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    # テストケース2: 0 XNOR 1 = 0
    gate.inputs = [SignalState.LOW, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    # テストケース3: 1 XNOR 0 = 0
    gate.inputs = [SignalState.HIGH, SignalState.LOW]
    result = gate.compute()
    assert result == SignalState.LOW, f"Expected LOW, got {result}"
    
    # テストケース4: 1 XNOR 1 = 1
    gate.inputs = [SignalState.HIGH, SignalState.HIGH]
    result = gate.compute()
    assert result == SignalState.HIGH, f"Expected HIGH, got {result}"
    
    print("✓ XNOR Gate test passed")


def test_circuit_simulation():
    """回路シミュレーションのテスト"""
    print("Testing Circuit Simulation...")
    
    # 簡単な回路を作成: 2つの入力とANDゲートと出力
    circuit = Circuit()
    
    # 入力ソース
    input1 = InputSource(0, 0, circuit.get_next_comp_id())
    input1.set_state(SignalState.HIGH)
    circuit.add_component(input1)
    
    input2 = InputSource(0, 0, circuit.get_next_comp_id())
    input2.set_state(SignalState.HIGH)
    circuit.add_component(input2)
    
    # ANDゲート
    and_gate = ANDGate(0, 0, circuit.get_next_comp_id())
    circuit.add_component(and_gate)
    
    # 出力ディスプレイ
    output = OutputDisplay(0, 0, circuit.get_next_comp_id())
    circuit.add_component(output)
    
    # 配線
    wire1 = Wire(circuit.get_next_wire_id(), input1.id, and_gate.id, 0)
    circuit.add_wire(wire1)
    
    wire2 = Wire(circuit.get_next_wire_id(), input2.id, and_gate.id, 1)
    circuit.add_wire(wire2)
    
    wire3 = Wire(circuit.get_next_wire_id(), and_gate.id, output.id, 0)
    circuit.add_wire(wire3)
    
    # シミュレーション実行
    circuit.simulate()
    
    # 結果確認: 1 AND 1 = 1
    assert output.output == SignalState.HIGH, f"Expected HIGH, got {output.output}"
    
    # 入力を変更
    input1.set_state(SignalState.LOW)
    circuit.simulate()
    
    # 結果確認: 0 AND 1 = 0
    assert output.output == SignalState.LOW, f"Expected LOW, got {output.output}"
    
    print("✓ Circuit Simulation test passed")


def test_circuit_save_load():
    """回路の保存と読み込みのテスト"""
    print("Testing Circuit Save/Load...")
    
    # 回路を作成
    circuit1 = Circuit()
    input1 = InputSource(100, 100, circuit1.get_next_comp_id())
    and_gate = ANDGate(200, 200, circuit1.get_next_comp_id())
    
    circuit1.add_component(input1)
    circuit1.add_component(and_gate)
    
    wire = Wire(circuit1.get_next_wire_id(), input1.id, and_gate.id, 0)
    circuit1.add_wire(wire)
    
    # 辞書に変換
    data = circuit1.to_dict()
    
    # 新しい回路を作成して復元
    circuit2 = Circuit()
    circuit2.from_dict(data)
    
    # 検証
    assert len(circuit2.components) == 2, f"Expected 2 components, got {len(circuit2.components)}"
    assert len(circuit2.wires) == 1, f"Expected 1 wire, got {len(circuit2.wires)}"
    
    print("✓ Circuit Save/Load test passed")


def run_all_tests():
    """全てのテストを実行"""
    print("=" * 50)
    print("Circuit Simulator - Unit Tests")
    print("=" * 50)
    print()
    
    try:
        test_and_gate()
        test_or_gate()
        test_not_gate()
        test_nand_gate()
        test_nor_gate()
        test_xor_gate()
        test_xnor_gate()
        test_circuit_simulation()
        test_circuit_save_load()
        
        print()
        print("=" * 50)
        print("All tests passed! ✓")
        print("=" * 50)
        return True
    except AssertionError as e:
        print()
        print("=" * 50)
        print(f"Test failed! ✗")
        print(f"Error: {e}")
        print("=" * 50)
        return False
    except Exception as e:
        print()
        print("=" * 50)
        print(f"Unexpected error! ✗")
        print(f"Error: {e}")
        print("=" * 50)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
