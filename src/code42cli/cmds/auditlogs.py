from collections import OrderedDict
from collections import defaultdict
from datetime import datetime
from datetime import timezone

import click

from code42cli.click_ext.groups import OrderedGroup
from code42cli.cmds.search.cursor_store import AuditLogCursorStore
from code42cli.cmds.search.options import BeginOption
from code42cli.date_helper import parse_max_timestamp
from code42cli.date_helper import parse_min_timestamp
from code42cli.logger import get_logger_for_server
from code42cli.options import begin_option
from code42cli.options import end_option
from code42cli.options import format_option
from code42cli.options import sdk_options
from code42cli.options import send_to_format_options
from code42cli.options import server_options
from code42cli.output_formats import OutputFormatter
from code42cli.util import warn_interrupt
from code42cli.util import hash_event

EVENT_KEY = "events"
AUDIT_LOGS_KEYWORD = "audit-logs"
AUDIT_LOG_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"

AUDIT_LOGS_DEFAULT_HEADER = OrderedDict()
AUDIT_LOGS_DEFAULT_HEADER["timestamp"] = "Timestamp"
AUDIT_LOGS_DEFAULT_HEADER["type$"] = "Type"
AUDIT_LOGS_DEFAULT_HEADER["actorName"] = "ActorName"
AUDIT_LOGS_DEFAULT_HEADER["actorIpAddress"] = "ActorIpAddress"
AUDIT_LOGS_DEFAULT_HEADER["userName"] = "AffectedUser"
AUDIT_LOGS_DEFAULT_HEADER["userId"] = "AffectedUserUID"


filter_option_usernames = click.option(
    "--username", required=False, help="Filter results by usernames.", multiple=True,
)
filter_option_user_ids = click.option(
    "--user-id", required=False, help="Filter results by user ids.", multiple=True,
)

filter_option_user_ip_addresses = click.option(
    "--user-ip",
    required=False,
    help="Filter results by user ip addresses.",
    multiple=True,
)
filter_option_affected_user_ids = click.option(
    "--affected-user-id",
    required=False,
    help="Filter results by affected user ids.",
    multiple=True,
)
filter_option_affected_usernames = click.option(
    "--affected-username",
    required=False,
    help="Filter results by affected usernames.",
    multiple=True,
)
filter_option_event_types = click.option(
    "--event-type",
    required=False,
    help="Filter results by event types.",
    multiple=True,
)


def filter_options(f):
    f = begin_option(
        f,
        AUDIT_LOGS_KEYWORD,
        callback=lambda ctx, param, arg: parse_min_timestamp(arg),
        cls=BeginOption,
    )
    f = end_option(
        f, AUDIT_LOGS_KEYWORD, callback=lambda ctx, param, arg: parse_max_timestamp(arg)
    )
    f = filter_option_event_types(f)
    f = filter_option_usernames(f)
    f = filter_option_user_ids(f)
    f = filter_option_user_ip_addresses(f)
    f = filter_option_affected_user_ids(f)
    f = filter_option_affected_usernames(f)
    return f


checkpoint_option = click.option(
    "-c",
    "--use-checkpoint",
    help="Only get audit-log events that were not previously retrieved.",
)


@click.group(cls=OrderedGroup)
@sdk_options(hidden=True)
def audit_logs(state):
    """Retrieve audit logs."""
    # store cursor getter on the group state so shared --begin option can use it in validation
    state.cursor_getter = _get_audit_log_cursor_store


@audit_logs.command()
@click.argument("checkpoint-name")
@sdk_options()
def clear_checkpoint(state, checkpoint_name):
    """Remove the saved file event checkpoint from `--use-checkpoint/-c` mode."""
    _get_audit_log_cursor_store(state.profile.name).delete(checkpoint_name)


@audit_logs.command()
@filter_options
@format_option
@checkpoint_option
@sdk_options()
def search(
    state,
    begin,
    end,
    event_type,
    username,
    user_id,
    user_ip,
    affected_user_id,
    affected_username,
    format,
    use_checkpoint,
):
    """Search audit logs."""
    formatter = OutputFormatter(format, AUDIT_LOGS_DEFAULT_HEADER)
    cursor = _get_audit_log_cursor_store(state.profile.name)
    if use_checkpoint:
        checkpoint = cursor.get(use_checkpoint)
        if checkpoint is not None:
            begin = checkpoint
    
    events = _get_all_audit_log_events(
        state.sdk,
        begin_time=begin,
        end_time=end,
        event_types=event_type,
        usernames=username,
        user_ids=user_id,
        user_ip_addresses=user_ip,
        affected_user_ids=affected_user_id,
        affected_usernames=affected_username
    )
    if use_checkpoint:
        events = list(_dedupe_checkpointed_events_and_store_updated_checkpoint(cursor, use_checkpoint, events))
    if not events:
        click.echo("No results found.")
        return
    elif len(events) > 10:
        click.echo_via_pager(formatter.get_formatted_output(events))
    else:
        formatter.echo_formatted_list(events)


@audit_logs.command()
@filter_options
@checkpoint_option
@server_options
@send_to_format_options
@sdk_options()
def send_to(
    state,
    hostname,
    protocol,
    format,
    begin,
    end,
    event_type,
    username,
    user_id,
    user_ip,
    affected_user_id,
    affected_username,
    use_checkpoint,
):
    """Send audit logs to the given server address."""
    logger = get_logger_for_server(hostname, protocol, format)
    cursor = _get_audit_log_cursor_store(state.profile.name)
    if use_checkpoint:
        checkpoint = cursor.get(use_checkpoint)
        if checkpoint is not None:
            begin = checkpoint

    events = _get_all_audit_log_events(
        state.sdk,
        begin_time=begin,
        end_time=end,
        event_types=event_type,
        usernames=username,
        user_ids=user_id,
        user_ip_addresses=user_ip,
        affected_user_ids=affected_user_id,
        affected_usernames=affected_username
    )
    if use_checkpoint:
        events = _dedupe_checkpointed_events_and_store_updated_checkpoint(cursor, use_checkpoint, events)
    with warn_interrupt():
        event = None
        for event in events:
            logger.info(event)
        if event is None:  # generator was empty
            click.echo("No results found.")


def _get_all_audit_log_events(sdk, **filter_args):
    response_gen = sdk.auditlogs.get_all(**filter_args)
    events = []
    try:
        responses = list(response_gen)
    except KeyError:
        # API endpoint (get_page) returns a response without events key when no records are found
        # e.g {"paginationRangeStartIndex": 10000, "paginationRangeEndIndex": 10000, "totalResultCount": 1593}
        # we can remove this check once PL-93211 is resolved and deployed.
        return events
    
    for response in responses:
        if EVENT_KEY in response.data:
            response_events = response.data.get(EVENT_KEY)
            events.extend(response_events)

    return sorted(events, key=lambda x: x.get("timestamp"))


def _dedupe_checkpointed_events_and_store_updated_checkpoint(cursor, checkpoint_name, events):
    checkpoint_events = cursor.get_events(checkpoint_name)
    new_timestamp = None
    new_events = []
    for event in events:
        event_hash = hash_event(event)
        if event_hash not in checkpoint_events:
            if event["timestamp"] != new_timestamp:
                new_timestamp = event["timestamp"]
                new_events.clear()
            new_events.append(event_hash)
            yield event
            ts = _parse_audit_log_timestamp_string_to_timestamp(new_timestamp)
            cursor.replace(checkpoint_name, ts)
            cursor.replace_events(checkpoint_name, new_events)


def _get_audit_log_cursor_store(profile_name):
    return AuditLogCursorStore(profile_name)


def _parse_audit_log_timestamp_string_to_timestamp(ts):
    # example: {"property": "bar", "timestamp": "2020-11-23T17:13:26.239647Z"}
    ts = ts[:-1]
    dt = datetime.strptime(ts, AUDIT_LOG_TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    return dt.timestamp()
