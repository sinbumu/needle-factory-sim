from needle_factory_sim.controller import FactoryController
from needle_factory_sim.models import SimulationStatus


def controller_with_robot_in_c() -> FactoryController:
    c = FactoryController()
    c.set_temperature("A", 30)
    c.set_temperature("C", 30)
    c.advance_time(10)
    assert c.move_robot("A").accepted
    assert c.move_robot("C").accepted
    return c


def test_c_entry_sets_used():
    c = controller_with_robot_in_c()
    assert c.state.sectors["C"].used is True
    assert c.state.sectors["C"].needs_reset is False


def test_c_leave_sets_needs_reset():
    c = controller_with_robot_in_c()
    assert c.move_robot("A").accepted
    assert c.state.sectors["C"].needs_reset is True


def test_reset_while_inside_rejected():
    c = controller_with_robot_in_c()
    result = c.reset_sector("C")
    assert not result.accepted
    assert result.error_code == "RESET_WHILE_INSIDE"


def test_reset_not_required_rejected():
    c = FactoryController()
    result = c.reset_sector("C")
    assert not result.accepted
    assert result.error_code == "RESET_NOT_REQUIRED"


def test_reset_outside_clears_flags_and_keeps_temperature():
    c = controller_with_robot_in_c()
    assert c.move_robot("A").accepted
    temp_before = c.state.sectors["C"].current_temperature
    target_before = c.state.sectors["C"].target_temperature
    result = c.reset_sector("C")
    assert result.accepted
    assert c.state.sectors["C"].used is False
    assert c.state.sectors["C"].needs_reset is False
    assert c.state.sectors["C"].current_temperature == temp_before
    assert c.state.sectors["C"].target_temperature == target_before


def test_goal_via_c_requires_cleanup_then_success():
    c = controller_with_robot_in_c()
    assert c.move_robot("E").accepted  # E is 30°C, adjacent to C
    assert c.state.sectors["C"].needs_reset is True
    assert c.state.status is SimulationStatus.GOAL_REACHED_CLEANUP_REQUIRED
    result = c.reset_sector("C")  # allowed while standing on E
    assert result.accepted
    assert c.state.status is SimulationStatus.MISSION_SUCCESS


def test_reset_simulation_restores_initial_state():
    c = controller_with_robot_in_c()
    c.emergency_stop()
    c.reset_simulation()
    state = c.state
    assert state.robot_sector == "S"
    assert state.cargo_hp == 100
    assert state.status is SimulationStatus.RUNNING
    assert state.sectors["A"].current_temperature == 10
    assert state.sectors["A"].target_temperature == 10
    assert state.sectors["B"].current_temperature == 55
    assert state.sectors["B"].door_open is False
    assert state.sectors["C"].used is False
    assert state.sectors["C"].needs_reset is False
