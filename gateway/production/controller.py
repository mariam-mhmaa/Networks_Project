"""Shared lifecycle/recovery controller with production-specific result validation."""
from gateway.inspection.controller import Controller
from gateway.inspection.wire import ProtocolError, uint

class ProductionController(Controller):
    @staticmethod
    def _result(result, request, duration_ms, expected_settings=None, completion_allowance_ms=None):
        if request["type"] == "RETIRE":
            return Controller._result(result, request, duration_ms, expected_settings, completion_allowance_ms)
        if (not isinstance(result, dict) or not Controller._identity(
                {**result, "boot_id": request["boot_id"]}, request) or
                result.get("state") != "COMPLETED" or
                not uint(result.get("elapsed_ms"), 2**53-1) or
                not uint(result.get("config_version"), minimum=1)):
            raise ProtocolError("invalid production result identity/state/version")
        settings=result.get("settings")
        if (not isinstance(settings, dict) or set(settings) != {"production_time_ms"} or
                not uint(settings["production_time_ms"], 600000, 1)):
            raise ProtocolError("invalid applied production settings")
        if request["type"] == "CONFIGURE" and settings != {"production_time_ms": request["production_time_ms"]}:
            raise ProtocolError("A did not confirm requested settings")
        if request["type"] == "PRODUCE":
            if (result.get("produced") is not True or "verdict" in result or
                    result["config_version"] != request["config_version"] or
                    (expected_settings is not None and settings != expected_settings) or
                    result["elapsed_ms"] < duration_ms or
                    (completion_allowance_ms is not None and result["elapsed_ms"] > duration_ms+completion_allowance_ms)):
                raise ProtocolError("invalid production execution evidence")
        if request["type"] == "CLOSE" and result.get("closed") is not True:
            raise ProtocolError("A did not confirm run closure")
        return result
