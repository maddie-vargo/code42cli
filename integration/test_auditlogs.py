from datetime import datetime
from datetime import timedelta

import pytest
from integration import run_command
from integration.util import DockerDaemon
from integration.util import SyslogServer


BASE_COMMAND = "code42 audit-logs search -b"
begin_date = datetime.utcnow() - timedelta(days=-10)
begin_date_str = begin_date.strftime("%Y-%m-%d %H:%M:%S")


@pytest.fixture
def data_transfer():
    with DockerDaemon():
        print("docker daemon started")
        with SyslogServer():
            print("syslog server started")
            yield run_command


@pytest.mark.parametrize("command", [("{} '{}'".format(BASE_COMMAND, begin_date_str))])
def test_auditlogs_search(command):
    return_code, response = run_command(command)
    assert return_code == 0


@pytest.mark.parametrize(
    "command",
    [
        (
            "code42 audit-logs '{}' send-to localhost -b 2020-12-08 -p TCP".format(
                begin_date_str
            )
        )
    ],
)
def test_auditlogs_send_to(data_transfer, command):
    exit_status, response = data_transfer(command)
    print(exit_status)
    print(response)
    assert exit_status == 0
