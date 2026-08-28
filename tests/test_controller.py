from needle_factory_sim.controller import FactoryController
from needle_factory_sim.models import SimulationStatus


def make() -> FactoryController:
    return FactoryController()


def test_move_not_adjacent_rejected():
    c = make()
    result = c.move_robot("E")
    assert not result.accepted
    assert result.error_code == "NOT_ADJACENT"
    assert not result.state_changed
    assert c.state.robot_sector == "S"


def test_move_to_cold_sector_rejected():
    c = make()
    result = c.move_robot("A")  # A starts at 10°C (COLD)
    assert not result.accepted
    assert result.error_code == "UNSAFE_TEMPERATURE"
    assert c.state.robot_sector == "S"


def test_set_temperature_changes_target_only():
    c = make()
    result = c.set_temperature("A", 30)
    assert result.accepted
    assert c.state.sectors["A"].target_temperature == 30
    assert c.state.sectors["A"].current_temperature == 10  # unchanged until time passes


def test_set_temperature_out_of_range_rejected():
    c = make()
    result = c.set_temperature("A", 61)
    assert not result.accepted
    assert result.error_code == "INVALID_TEMPERATURE"
    assert c.state.sectors["A"].target_temperature == 10


def test_set_temperature_invalid_sector_rejected():
    c = make()
    result = c.set_temperature("X", 30)
    assert not result.accepted
    assert result.error_code == "INVALID_SECTOR"


def test_enter_b_with_closed_door_rejected():
    c = make()
    c.set_temperature("A", 30)
    c.set_temperature("B", 30)
    c.advance_time(10)  # both reach safe temps
    c.move_robot("A")
    result = c.move_robot("B")
    assert not result.accepted
    assert result.error_code == "DOOR_CLOSED"
    assert c.state.robot_sector == "A"


def test_enter_b_with_open_door_and_safe_temp_accepted():
    c = make()
    c.set_temperature("A", 30)
    c.set_temperature("B", 30)
    c.advance_time(10)
    c.toggle_door("B", True)
    assert c.move_robot("A").accepted
    result = c.move_robot("B")
    assert result.accepted
    assert c.state.robot_sector == "B"


def test_temperature_transition_rate():
    c = make()
    c.set_temperature("A", 30)
    c.advance_time(1.0)
    assert c.state.sectors["A"].current_temperature == 20  # 10 + 10*1
    c.advance_time(0.5)
    assert c.state.sectors["A"].current_temperature == 25
    c.advance_time(10)
    assert c.state.sectors["A"].current_temperature == 30  # clamped at target


def test_cargo_damage_and_game_over():
    c = make()
    c.state.sectors["S"].current_temperature = 50  # force unsafe at robot position
    c.state.sectors["S"].target_temperature = 50
    c.advance_time(1.0)
    assert c.state.cargo_hp == 90
    c.advance_time(20.0)
    assert c.state.cargo_hp == 0
    assert c.state.status is SimulationStatus.GAME_OVER
    result = c.move_robot("A")
    assert not result.accepted
    assert result.error_code == "GAME_OVER"


def test_emergency_stop_blocks_actions_and_time():
    c = make()
    c.emergency_stop()
    assert c.state.status is SimulationStatus.EMERGENCY_STOPPED
    result = c.set_temperature("A", 30)
    assert not result.accepted
    assert result.error_code == "EMERGENCY_STOPPED"
    c.set_temperature("A", 30)
    before = c.state.sectors["A"].current_temperature
    c.advance_time(5)
    assert c.state.sectors["A"].current_temperature == before  # time paused


def test_mission_success_via_b_route():
    c = make()
    c.set_temperature("A", 30)
    c.set_temperature("B", 30)
    c.advance_time(10)
    c.toggle_door("B", True)
    assert c.move_robot("A").accepted
    assert c.move_robot("B").accepted
    assert c.move_robot("E").accepted
    assert c.state.status is SimulationStatus.MISSION_SUCCESS
