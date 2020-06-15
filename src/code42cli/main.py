import platform
import signal
import sys

from py42.settings import set_user_agent_suffix

from code42cli import PRODUCT_NAME

# from code42cli.cmds.detectionlists import departing_employee as de
# from code42cli.cmds.detectionlists import high_risk_employee as hre
# from code42cli.cmds.detectionlists.enums import DetectionLists
# from code42cli.cmds.securitydata import main as secmain
# from code42cli.cmds.alerts import main as alertmain
# from code42cli.cmds.alerts.rules import commands as alertrules
from code42cli.cmds.legal_hold import legal_hold
from code42cli.cmds.profile import profile
from code42cli.commands import Command, SubcommandLoader
from code42cli.invoker import CommandInvoker
from code42cli.util import flush_stds_out_err_without_printing_error
from code42cli.sdk_client import create_sdk

import click

# Handle KeyboardInterrupts by just exiting instead of printing out a stack
def exit_on_interrupt(signal, frame):
    print()
    sys.exit(1)


signal.signal(signal.SIGINT, exit_on_interrupt)


# If on Windows, configure console session to handle ANSI escape sequences correctly
# source: https://bugs.python.org/issue29059
if platform.system().lower() == u"windows":
    from ctypes import windll, c_int, byref

    stdout_handle = windll.kernel32.GetStdHandle(c_int(-11))
    mode = c_int(0)
    windll.kernel32.GetConsoleMode(c_int(stdout_handle), byref(mode))
    mode = c_int(mode.value | 4)
    windll.kernel32.SetConsoleMode(c_int(stdout_handle), mode)


# Sets part of the user agent string that py42 attaches to requests for the purposes of
# identifying CLI users.
set_user_agent_suffix(PRODUCT_NAME)


@click.group()
@click.option("--debug", is_flag=True)
@click.option("--profile")
def code42(profile, debug):
    if not profile:
        profile = 
    sdk = create_sdk(profile, is_debug_mode=debug)


code42.add_command(profile)
code42.add_command(legal_hold)


def main():
    try:
        code42()
    finally:
        flush_stds_out_err_without_printing_error()


if __name__ == u"__main__":
    main()
