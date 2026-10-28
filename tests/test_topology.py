from netproof.topology import load_topology


def test_path_staff_to_fileserver():
    t = load_topology()
    assert t.path_nodes("pc-staff", "fileserver") == {"pc-staff", "r-edge", "r-core", "fileserver"}


def test_path_guest_to_staff_stays_at_edge():
    t = load_topology()
    assert t.path_nodes("pc-guest", "pc-staff") == {"pc-guest", "r-edge", "pc-staff"}


def test_hosts_do_not_forward():
    t = load_topology()
    # fileserver and webserver share a subnet: direct, no router in between
    assert t.path_nodes("fileserver", "webserver") == {"fileserver", "webserver"}


def test_resolve_and_ips():
    t = load_topology()
    assert t.resolve("r-core") == "10.10.9.2"
    assert t.resolve("10.10.3.10") == "10.10.3.10"
    assert "10.10.1.254" not in t.node_ips()
