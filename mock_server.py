"""
Circuit Provider Mock Server
Simulates Megaport and Equinix Fabric v4 APIs for the circuit scaling demo.
Response schemas match the real provider APIs exactly.
"""

import json
import os
import time
import copy
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response

app = Flask(__name__)

MEGAPORT_DELAY_SECONDS = int(os.environ.get("MEGAPORT_DELAY_SECONDS", 3))
EQUINIX_POLL_ROUNDS = int(os.environ.get("EQUINIX_POLL_ROUNDS", 3))

VALID_EQUINIX_BANDWIDTHS = {10, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 25000, 50000, 100000}

# Load seed data and keep a reset copy
with open("seed-data.json") as f:
    _seed = json.load(f)

def _build_state(seed):
    return {c["circuit_id"]: copy.deepcopy(c) for c in seed["circuits"]}

state = _build_state(_seed)


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _circuit(circuit_id):
    c = state.get(circuit_id)
    if not c:
        return None, jsonify({"message": f"Product [{circuit_id}] not found.", "terms": "This data is subject to the Acceptable Use Policy", "data": None}), 404
    return c, None, None


# ---------------------------------------------------------------------------
# MEGAPORT ROUTES
# ---------------------------------------------------------------------------

@app.route("/megaport/v3/product/vxc/<product_uid>", methods=["PUT"])
def megaport_update_vxc(product_uid):
    """Change VXC rateLimit. Synchronous — returns 200 when done."""
    c, err, code = _circuit(product_uid)
    if err:
        return err, code

    body = request.get_json(silent=True) or {}
    rate_limit = body.get("rateLimit")

    if rate_limit is None:
        return jsonify({"message": "Validation failed", "terms": "This data is subject to the Acceptable Use Policy", "data": "rateLimit is required"}), 400

    if not isinstance(rate_limit, int) or rate_limit <= 0:
        return jsonify({"message": "Validation failed", "terms": "This data is subject to the Acceptable Use Policy", "data": "rateLimit must be a positive integer (Mbps)"}), 400

    if rate_limit > c["max_rate_mbps"]:
        return jsonify({"message": "Validation failed", "terms": "This data is subject to the Acceptable Use Policy", "data": f"Requested rate limit {rate_limit} exceeds maximum path capacity {c['max_rate_mbps']}"}), 422

    time.sleep(MEGAPORT_DELAY_SECONDS)

    c["rate_limit_mbps"] = rate_limit
    c["provisioning_status"] = "CONFIGURED"

    return jsonify({
        "message": f"VXC [{product_uid}] updated.",
        "terms": "This data is subject to the Acceptable Use Policy",
        "data": {
            "productUid": product_uid,
            "productName": c["name"],
            "productType": "VXC",
            "rateLimit": c["rate_limit_mbps"],
            "maximumRate": c["max_rate_mbps"],
            "provisioningStatus": c["provisioning_status"],
            "up": c.get("up", True),
            "liveDate": c.get("live_date", _now_iso()),
            "createDate": c.get("create_date", _now_iso())
        }
    }), 200


@app.route("/megaport/v2/product/<product_uid>", methods=["GET"])
def megaport_get_product(product_uid):
    """Get current VXC status and rateLimit."""
    c, err, code = _circuit(product_uid)
    if err:
        return err, code

    return jsonify({
        "message": f"Service [{product_uid}] details.",
        "terms": "This data is subject to the Acceptable Use Policy",
        "data": {
            "productUid": product_uid,
            "productName": c["name"],
            "productType": "VXC",
            "rateLimit": c["rate_limit_mbps"],
            "maximumRate": c["max_rate_mbps"],
            "provisioningStatus": c.get("provisioning_status", "LIVE"),
            "up": c.get("up", True),
            "liveDate": c.get("live_date", _now_iso()),
            "createDate": c.get("create_date", _now_iso())
        }
    }), 200


@app.route("/megaport/v1/openmetrics", methods=["GET"])
def megaport_openmetrics():
    """
    Prometheus/OpenMetrics endpoint for all Megaport VXCs.
    Returns cumulative byte/packet counters per VXC.
    Counters increment slightly each call to simulate live traffic.
    """
    lines = []
    lines.append("# HELP megaport_service_receive_bytes_total Total bytes received")
    lines.append("# TYPE megaport_service_receive_bytes_total counter")
    for cid, c in state.items():
        if c.get("provider") != "megaport":
            continue
        # Increment counter to simulate traffic
        c["receive_bytes_total"] += int(c["rate_limit_mbps"] * 1000 * 0.3)
        lines.append(f'megaport_service_receive_bytes_total{{service_uid="{cid}",service_type="VXC",service_name="{c["name"]}"}} {c["receive_bytes_total"]}')

    lines.append("# HELP megaport_service_transmit_bytes_total Total bytes transmitted")
    lines.append("# TYPE megaport_service_transmit_bytes_total counter")
    for cid, c in state.items():
        if c.get("provider") != "megaport":
            continue
        c["transmit_bytes_total"] += int(c["rate_limit_mbps"] * 1000 * 0.25)
        lines.append(f'megaport_service_transmit_bytes_total{{service_uid="{cid}",service_type="VXC",service_name="{c["name"]}"}} {c["transmit_bytes_total"]}')

    lines.append("# HELP megaport_service_receive_packets_total Total packets received")
    lines.append("# TYPE megaport_service_receive_packets_total counter")
    for cid, c in state.items():
        if c.get("provider") != "megaport":
            continue
        c["receive_packets_total"] += int(c["rate_limit_mbps"] * 0.27)
        lines.append(f'megaport_service_receive_packets_total{{service_uid="{cid}",service_type="VXC",service_name="{c["name"]}"}} {c["receive_packets_total"]}')

    lines.append("# HELP megaport_service_transmit_packets_total Total packets transmitted")
    lines.append("# TYPE megaport_service_transmit_packets_total counter")
    for cid, c in state.items():
        if c.get("provider") != "megaport":
            continue
        c["transmit_packets_total"] += int(c["rate_limit_mbps"] * 0.22)
        lines.append(f'megaport_service_transmit_packets_total{{service_uid="{cid}",service_type="VXC",service_name="{c["name"]}"}} {c["transmit_packets_total"]}')

    lines.append("# HELP megaport_service_up Operational status of the service (1=up, 0=down)")
    lines.append("# TYPE megaport_service_up gauge")
    for cid, c in state.items():
        if c.get("provider") != "megaport":
            continue
        up_val = 1 if c.get("up", True) else 0
        lines.append(f'megaport_service_up{{service_uid="{cid}",service_type="VXC",service_name="{c["name"]}"}} {up_val}')

    lines.append("# EOF")
    return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4; charset=utf-8")


# ---------------------------------------------------------------------------
# EQUINIX ROUTES
# ---------------------------------------------------------------------------

@app.route("/equinix/fabric/v4/connections/<connection_id>", methods=["PATCH"])
def equinix_update_connection(connection_id):
    """
    Change connection bandwidth. Async — returns 202 immediately.
    Poll GET until operation.equinixStatus = PROVISIONED.
    Expects JSON Patch RFC 6902: [{"op":"replace","path":"/bandwidth","value":5000}]
    """
    c, err, code = _circuit(connection_id)
    if err:
        return err, code

    ops = request.get_json(silent=True)
    if not isinstance(ops, list) or not ops:
        return jsonify({"errorCode": "BAD_REQUEST", "message": "Body must be a JSON Patch array"}), 400

    # Find the /bandwidth replace op
    new_bandwidth = None
    for op in ops:
        if op.get("op") == "replace" and op.get("path") == "/bandwidth":
            new_bandwidth = op.get("value")
            break

    if new_bandwidth is None:
        return jsonify({"errorCode": "BAD_REQUEST", "message": "JSON Patch must include op=replace path=/bandwidth"}), 400

    if not isinstance(new_bandwidth, int) or new_bandwidth not in VALID_EQUINIX_BANDWIDTHS:
        return jsonify({"errorCode": "INVALID_BANDWIDTH", "message": f"Requested bandwidth {new_bandwidth} is not supported. Valid values (Mbps): {sorted(VALID_EQUINIX_BANDWIDTHS)}"}), 400

    if new_bandwidth > c["max_rate_mbps"]:
        return jsonify({"errorCode": "CAPACITY_EXCEEDED", "message": f"Requested bandwidth {new_bandwidth} exceeds port capacity {c['max_rate_mbps']}"}), 422

    # Set async state
    c["pending_bandwidth_mbps"] = new_bandwidth
    c["equinix_status"] = "PROVISIONING"
    c["provider_status"] = "PROVISIONING"
    c["poll_counter"] = 0
    c["updated_date"] = _now_iso()

    return jsonify({
        "uuid": connection_id,
        "name": c["name"],
        "type": c.get("type", "EVPL_VC"),
        "bandwidth": new_bandwidth,
        "operation": {
            "equinixStatus": "PROVISIONING",
            "providerStatus": "PROVISIONING"
        },
        "changeLog": {
            "updatedDateTime": c["updated_date"]
        }
    }), 202


@app.route("/equinix/fabric/v4/connections/<connection_id>", methods=["GET"])
def equinix_get_connection(connection_id):
    """Poll connection status. Transitions PROVISIONING → PROVISIONED after EQUINIX_POLL_ROUNDS calls."""
    c, err, code = _circuit(connection_id)
    if err:
        return err, code

    if c.get("equinix_status") == "PROVISIONING":
        c["poll_counter"] = c.get("poll_counter", 0) + 1
        if c["poll_counter"] >= EQUINIX_POLL_ROUNDS:
            c["equinix_status"] = "PROVISIONED"
            c["provider_status"] = "PROVISIONED"
            if c.get("pending_bandwidth_mbps") is not None:
                c["rate_limit_mbps"] = c["pending_bandwidth_mbps"]
                c["pending_bandwidth_mbps"] = None
            c["updated_date"] = _now_iso()

    return jsonify({
        "uuid": connection_id,
        "name": c["name"],
        "type": c.get("type", "EVPL_VC"),
        "bandwidth": c.get("pending_bandwidth_mbps") or c["rate_limit_mbps"],
        "operation": {
            "equinixStatus": c.get("equinix_status", "PROVISIONED"),
            "providerStatus": c.get("provider_status", "PROVISIONED")
        },
        "changeLog": {
            "updatedDateTime": c.get("updated_date", _now_iso())
        }
    }), 200


@app.route("/equinix/fabric/v4/connections/<connection_id>/stats", methods=["GET"])
def equinix_connection_stats(connection_id):
    """
    Connection bandwidth utilization statistics.
    Returns BandwidthUtilization object matching Equinix Fabric v4 Statistics schema.
    Max/mean values derived from seeded utilization_pct × current rate_limit_mbps.
    """
    c, err, code = _circuit(connection_id)
    if err:
        return err, code

    start_dt = request.args.get("startDateTime", "2026-06-15T00:00:00Z")
    end_dt = request.args.get("endDateTime", "2026-06-15T12:00:00Z")
    view_point = request.args.get("viewPoint", "aSide")

    util = c.get("utilization_pct", 40) / 100.0
    rate = c["rate_limit_mbps"]
    inbound_max = round(rate * util * 1.05, 1)
    inbound_mean = round(rate * util * 0.95, 1)
    outbound_max = round(rate * util * 0.28, 1)
    outbound_mean = round(rate * util * 0.22, 1)

    return jsonify({
        "startDateTime": start_dt,
        "endDateTime": end_dt,
        "viewPoint": view_point,
        "bandwidthUtilization": {
            "unit": "Mbps",
            "metricInterval": "PT5M",
            "inbound": {
                "max": inbound_max,
                "mean": inbound_mean,
                "metrics": [
                    {"intervalEndTimestamp": "2026-06-15T00:05:00Z", "max": inbound_max, "mean": inbound_mean},
                    {"intervalEndTimestamp": "2026-06-15T00:10:00Z", "max": round(inbound_max * 0.97, 1), "mean": round(inbound_mean * 0.96, 1)}
                ]
            },
            "outbound": {
                "max": outbound_max,
                "mean": outbound_mean,
                "metrics": [
                    {"intervalEndTimestamp": "2026-06-15T00:05:00Z", "max": outbound_max, "mean": outbound_mean},
                    {"intervalEndTimestamp": "2026-06-15T00:10:00Z", "max": round(outbound_max * 0.98, 1), "mean": round(outbound_mean * 0.95, 1)}
                ]
            }
        }
    }), 200


# ---------------------------------------------------------------------------
# MOCK CONTROL PLANE
# ---------------------------------------------------------------------------

@app.route("/mock/seed/utilization/<circuit_id>", methods=["POST"])
def seed_utilization(circuit_id):
    """Seed utilization % for a circuit. Used to control alarm corroboration behavior."""
    c, err, code = _circuit(circuit_id)
    if err:
        return err, code

    body = request.get_json(silent=True) or {}
    pct = body.get("utilization_pct")
    if pct is None or not isinstance(pct, (int, float)) or not (0 <= pct <= 100):
        return jsonify({"ok": False, "error": "utilization_pct must be a number between 0 and 100"}), 400

    c["utilization_pct"] = pct
    return jsonify({"ok": True, "circuit_id": circuit_id, "utilization_pct": pct}), 200


@app.route("/mock/seed/bandwidth/<circuit_id>", methods=["POST"])
def seed_bandwidth(circuit_id):
    """Override current bandwidth without going through the provider API flow. For pre-staging demo state."""
    c, err, code = _circuit(circuit_id)
    if err:
        return err, code

    body = request.get_json(silent=True) or {}
    bw = body.get("bandwidth_mbps")
    if bw is None or not isinstance(bw, int) or bw <= 0:
        return jsonify({"ok": False, "error": "bandwidth_mbps must be a positive integer"}), 400

    c["rate_limit_mbps"] = bw
    if c.get("provider") == "equinix":
        c["equinix_status"] = "PROVISIONED"
        c["provider_status"] = "PROVISIONED"
    else:
        c["provisioning_status"] = "LIVE"

    return jsonify({"ok": True, "circuit_id": circuit_id, "bandwidth_mbps": bw}), 200


@app.route("/mock/reset", methods=["POST"])
def mock_reset():
    """Reset all circuit state to seed values."""
    global state
    state = _build_state(_seed)
    return jsonify({"ok": True, "message": "All circuit state reset to seed values"}), 200


@app.route("/mock/state", methods=["GET"])
def mock_state():
    """Return full in-memory state for all circuits. Debug use."""
    return jsonify({"circuits": list(state.values())}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
