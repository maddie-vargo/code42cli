import sys
import urllib3
import json
from argparse import ArgumentParser
from datetime import datetime, timedelta
from keyring import get_password, set_password
from getpass import getpass
from logging import StreamHandler, FileHandler, getLogger, INFO

import py42.debug_level as debug_level
from py42.sdk import SDK
from py42 import settings
from c42secevents.extractors import AEDEventExtractor
from c42secevents.common import FileEventHandlers
from c42secevents.logging.formatters import AEDDictToCEFFormatter, AEDDictToJSONFormatter
from c42secevents.logging.handlers import NoPrioritySysLogHandler

from c42seceventcli.common.common import (
    SecEventConfigParser,
    parse_timestamp,
    convert_date_to_timestamp,
)
from c42seceventcli.aed.aed_cursor_store import AEDCursorStore
from c42seceventcli.common.cli_args import (
    add_authority_host_address_arg,
    add_username_arg,
    add_begin_date_arg,
    add_end_date_arg,
    add_ignore_ssl_errors_arg,
    add_output_format_arg,
    add_record_cursor_arg,
    add_exposure_types_arg,
    add_debug_arg,
    add_destination_type_arg,
    add_destination_arg,
    add_syslog_port_arg,
    add_syslog_protocol_arg,
    add_help_arg,
)

_SERVICE_NAME_FOR_KEYCHAIN = u"c42seceventcli"


def main():
    parser = _get_arg_parser()
    cli_args = parser.parse_args()
    config_parser = _get_config_parser()
    args = _union_cli_args_with_config_args(cli_args, config_parser)

    _parse_ignore_ssl_errors(args)
    _parse_debug_mode(args)
    min_timestamp = _parse_min_timestamp(args)
    max_timestamp = _parse_max_timestamp(args)

    sdk = _create_sdk_from_args(args, parser)
    handlers = _create_handlers(args)
    extractor = AEDEventExtractor(sdk, handlers)
    extractor.extract(min_timestamp, max_timestamp, args.get("exposure_types"))


def _get_arg_parser():
    parser = ArgumentParser(add_help=False)

    # Makes sure that you can't give both an end_timestamp and record cursor positions
    mutually_exclusive_timestamp_group = parser.add_mutually_exclusive_group()
    add_end_date_arg(mutually_exclusive_timestamp_group)
    add_record_cursor_arg(mutually_exclusive_timestamp_group)

    main_args = parser.add_argument_group("main")
    add_authority_host_address_arg(main_args)
    add_username_arg(main_args)
    add_help_arg(main_args)
    add_begin_date_arg(main_args)
    add_ignore_ssl_errors_arg(main_args)
    add_output_format_arg(main_args)
    add_exposure_types_arg(main_args)
    add_debug_arg(main_args)
    add_destination_type_arg(main_args)
    add_destination_arg(main_args)
    add_syslog_port_arg(main_args)
    add_syslog_protocol_arg(main_args)
    return parser


def _get_config_parser():
    config = SecEventConfigParser("config.cfg")
    return config if config.is_valid else None


def _union_cli_args_with_config_args(cli_args, config_parser):
    return {
        "username": cli_args.c42_username
        if cli_args.c42_username
        else config_parser.parse_username(),
        "server": cli_args.c42_authority_url
        if cli_args.c42_authority_url
        else config_parser.parse_server(),
        "begin_date": cli_args.c42_begin_date
        if cli_args.c42_begin_date
        else config_parser.parse_begin_date(),
        "end_date": cli_args.c42_end_date
        if cli_args.c42_end_date
        else config_parser.parse_end_date(),
        "ignore_ssl_errors": cli_args.c42_ignore_ssl_errors
        if cli_args.c42_ignore_ssl_errors
        else config_parser.parse_ignore_ssl_errors(),
        "output_format": cli_args.c42_output_format
        if cli_args.c42_output_format
        else config_parser.parse_output_format(),
        "record_cursor": cli_args.c42_record_cursor
        if cli_args.c42_record_cursor
        else config_parser.parse_record_cursor(),
        "exposure_types": cli_args.c42_exposure_types
        if cli_args.c42_exposure_types
        else config_parser.parse_exposure_types(),
        "debug_mode": cli_args.c42_debug_mode
        if cli_args.c42_debug_mode
        else config_parser.parse_debug_mode(),
        "destination_type": cli_args.c42_destination_type
        if cli_args.c42_destination_type
        else config_parser.parse_destination_type(),
        "destination": cli_args.c42_destination
        if cli_args.c42_destination
        else config_parser.parse_destination(),
        "syslog_port": cli_args.c42_syslog_port
        if cli_args.c42_syslog_port
        else config_parser.parse_syslog_port(),
        "syslog_protocol": cli_args.c42_syslog_protocol
        if cli_args.c42_syslog_protocol
        else config_parser.parse_syslog_protocol(),
    }


def _ignore_ssl_errors():
    settings.verify_ssl_certs = False
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _parse_ignore_ssl_errors(args):
    if args.get("ignore_ssl_errors"):
        _ignore_ssl_errors()


def _parse_debug_mode(args):
    if args.get("debug_mode"):
        settings.debug_level = debug_level.DEBUG


def _parse_min_timestamp(args):
    min_timestamp = parse_timestamp(args.get("begin_date"))
    if not _verify_min_timestamp(min_timestamp):
        print("Argument --begin must be within 90 days")
        exit(1)

    return min_timestamp


def _verify_min_timestamp(min_timestamp):
    boundary_date = datetime.utcnow() - timedelta(days=90)
    boundary = convert_date_to_timestamp(boundary_date)
    return min_timestamp >= boundary


def _parse_max_timestamp(args):
    return parse_timestamp(args.get("end_date"))


def _create_sdk_from_args(args, parser):
    server = _parse_server_address(args, parser)
    username = _parse_username(args, parser)
    password = _get_password(username)
    sdk = SDK.create_using_local_account(host_address=server, username=username, password=password)
    return sdk


def _parse_server_address(args, parser):
    server = args.get("server")
    if server is None:
        _exit_from_argument_error("Host address not provided.", parser)

    return server


def _parse_username(args, parser):
    username = args.get("username")
    if username is None:
        _exit_from_argument_error("Username not provided.", parser)

    return username


def _exit_from_argument_error(message, parser):
    print(message)
    parser.print_usage()
    exit(1)


def _get_password(username):
    password = get_password(_SERVICE_NAME_FOR_KEYCHAIN, username)
    if password is None:
        pwd = getpass()
        set_password(_SERVICE_NAME_FOR_KEYCHAIN, username, pwd)

    return password


def _create_handlers(args):
    store = AEDCursorStore()
    handlers = FileEventHandlers()
    handlers.record_cursor_position = store.replace_stored_insertion_timestamp
    handlers.get_cursor_position = store.get_stored_insertion_timestamp
    logger = _get_logger(args)
    handlers.handle_response = _get_response_handler(logger)
    return handlers


def _get_logger(args):
    output_format = args.get("output_format")
    destination = args.get("destination")
    logger = getLogger("Code42_SecEventCli_Logger")
    formatter = _get_log_formatter(output_format)
    handler = _get_log_handler(args.get(destination))
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(INFO)
    return logger


def _get_log_formatter(output_format):
    if output_format == "JSON":
        return AEDDictToJSONFormatter()
    elif output_format == "CEF":
        return AEDDictToCEFFormatter()
    else:
        print("Unsupported output format {0}".format(output_format))
        exit(1)


def _get_log_handler(destination, destination_type="stdout"):
    if destination_type == "stdout":
        return StreamHandler(sys.stdout)
    elif destination_type == "syslog":
        return NoPrioritySysLogHandler(destination)
    elif destination_type == "file":
        return FileHandler(filename=destination)


def _get_response_handler(logger):
    def handle_response(response):
        response_dict = json.loads(response.text)
        file_events_key = u"fileEvents"
        if file_events_key in response_dict:
            events = response_dict[file_events_key]
            for event in events:
                logger.info(event)

    return handle_response


if __name__ == "__main__":
    main()
