import pytest
from app.simulation.engine import SimulationEngine
from app.simulation.scenario import ScenarioParser
import json
import logging

def test_simulation_determinism():
    # 1. Generate a complex scenario
    scenario_data = ScenarioParser.generate_random_scenario(seed=123, num_orders=3, num_partners=2)
    
    # Add a scripted disruption
    scenario_data["disruptions"].append({
        "type": "roadblock",
        "lat": scenario_data["orders"][0]["lat"], # near first order
        "lon": scenario_data["orders"][0]["lon"],
        "trigger_tick": 5
    })

    def run_sim():
        engine = SimulationEngine()
        engine.load_scenario(scenario_data)
        
        # Fast forward 15 ticks
        for _ in range(15):
            engine.advance_tick()
            
        # Extract a state fingerprint (total routes cost + status of stops)
        # Static world
        s_cost = sum(r.get("cost", 0) for r in engine.static_world.routes)
        s_statuses = [(s.id, s.status) for s in engine.static_world.stops.values()]
        
        # Dynamic world
        d_cost = sum(r.get("cost", 0) for r in engine.dynamic_world.routes)
        d_statuses = [(s.id, s.status) for s in engine.dynamic_world.stops.values()]
        
        return {
            "s_cost": s_cost,
            "s_statuses": s_statuses,
            "d_cost": d_cost,
            "d_statuses": d_statuses
        }

    run1 = run_sim()
    run2 = run_sim()
    
    assert run1["s_cost"] == run2["s_cost"]
    assert run1["s_statuses"] == run2["s_statuses"]
    assert run1["d_cost"] == run2["d_cost"]
    assert run1["d_statuses"] == run2["d_statuses"]

