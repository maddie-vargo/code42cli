import click

from code42cli.options import global_options
from code42cli.cmds.search_shared import logger_factory
from py42.sdk.queries.alerts.filters import *
from c42eventextractor.extractors import AlertExtractor

from code42cli.cmds.search_shared.options import (
    create_search_options,
    AdvancedQueryIncompatible,
    is_in_filter,
    contains_filter,
    not_contains_filter,
    not_in_filter,
    output_file_arg,
    server_options,
)

from code42cli.cmds.search_shared.enums import (
    AlertOutputFormat,
    AlertSeverity as AlertSeverityOptions,
    AlertState as AlertStateOptions,
    RuleType as RuleTypeOptions,
)
from code42cli.cmds.search_shared.cursor_store import AlertCursorStore
from code42cli.cmds.search_shared.extraction import (
    create_handlers,
    create_time_range_filter,
)

import code42cli.errors as errors
from code42cli.logger import get_main_cli_logger


logger = get_main_cli_logger()

search_options = create_search_options("alerts")

format_option = click.option(
    "-f",
    "--format",
    type=click.Choice(AlertOutputFormat()),
    default=AlertOutputFormat.JSON,
    help="The format used for outputting alerts.",
)
severity_option = click.option(
    "--severity",
    multiple=True,
    type=click.Choice(AlertSeverityOptions()),
    cls=AdvancedQueryIncompatible,
    callback=is_in_filter(Severity),
    help="Filter alerts by severity. Defaults to returning all severities.",
)
state_option = click.option(
    "--state",
    multiple=True,
    type=click.Choice(AlertStateOptions()),
    cls=AdvancedQueryIncompatible,
    callback=is_in_filter(AlertState),
    help="Filter alerts by state. Defaults to returning all states.",
)
actor_option = click.option(
    "--actor",
    multiple=True,
    cls=AdvancedQueryIncompatible,
    callback=is_in_filter(Actor),
    help="Filter alerts by including the given actor(s) who triggered the alert. "
    "Args must match actor username exactly.",
)
actor_contains_option = click.option(
    "--actor-contains",
    multiple=True,
    cls=AdvancedQueryIncompatible,
    callback=contains_filter(Actor),
    help="Filter alerts by including actor(s) whose username contains the given string.",
)
exclude_actor_option = click.option(
    "--exclude-actor",
    multiple=True,
    cls=AdvancedQueryIncompatible,
    callback=not_in_filter(Actor),
    help="Filter alerts by excluding the given actor(s) who triggered the alert. "
    "Args must match actor username exactly.",
)
exclude_actor_contains_option = click.option(
    "--exclude-actor-contains",
    multiple=True,
    cls=AdvancedQueryIncompatible,
    callback=not_contains_filter(Actor),
    help="Filter alerts by excluding actor(s) whose username contains the given string.",
)
rule_name_option = click.option(
    "--rule-name",
    multiple=True,
    cls=AdvancedQueryIncompatible,
    callback=is_in_filter(RuleName),
    help="Filter alerts by including the given rule name(s).",
)
exclude_rule_name_option = click.option(
    "--exclude-rule-name",
    multiple=True,
    cls=AdvancedQueryIncompatible,
    callback=not_in_filter(RuleName),
    help="Filter alerts by excluding the given rule name(s).",
)
rule_id_option = click.option(
    "--rule-id",
    multiple=True,
    cls=AdvancedQueryIncompatible,
    callback=is_in_filter(RuleId),
    help="Filter alerts by including the given rule id(s).",
)
exclude_rule_id_option = click.option(
    "--exclude-rule-id",
    multiple=True,
    cls=AdvancedQueryIncompatible,
    callback=not_in_filter(RuleId),
    help="Filter alerts by excluding the given rule id(s).",
)
rule_type_option = click.option(
    "--rule-type",
    multiple=True,
    type=click.Choice(RuleTypeOptions()),
    cls=AdvancedQueryIncompatible,
    callback=is_in_filter(RuleType),
    help="Filter alerts by including the given rule type(s).",
)
exclude_rule_type_option = click.option(
    "--exclude-rule-type",
    multiple=True,
    cls=AdvancedQueryIncompatible,
    callback=not_in_filter(RuleType),
    help="Filter alerts by excluding the given rule type(s).",
)
description_option = click.option(
    "--description",
    multiple=True,
    cls=AdvancedQueryIncompatible,
    callback=contains_filter(Description),
    help="Filter alerts by description. Does fuzzy search by default.",
)


def alert_options(f):
    f = actor_option(f)
    f = actor_contains_option(f)
    f = exclude_actor_option(f)
    f = exclude_actor_contains_option(f)
    f = rule_name_option(f)
    f = exclude_rule_name_option(f)
    f = rule_id_option(f)
    f = exclude_rule_id_option(f)
    f = rule_type_option(f)
    f = exclude_rule_type_option(f)
    f = description_option(f)
    f = severity_option(f)
    f = state_option(f)
    f = format_option(f)
    return f


@click.group()
@global_options
def alerts(state):
    state.cursor = AlertCursorStore(state.profile.name)


@alerts.command()
@global_options
def clear_checkpoint(state):
    state.cursor.replace_stored_cursor_timestamp(None)


@alerts.command("print")
@alert_options
@search_options
@global_options
def _print(cli_state, format, begin, end, advanced_query, incremental, **kwargs):
    output_logger = logger_factory.get_logger_for_stdout(format)
    _extract(
        cli_state.sdk,
        cli_state.profile,
        cli_state.search_filters,
        begin,
        end,
        advanced_query,
        incremental,
        output_logger,
    )


@alerts.command()
@output_file_arg
@alert_options
@search_options
@global_options
def write_to(cli_state, format, output_file, begin, end, advanced_query, incremental, **kwargs):
    output_logger = logger_factory.get_logger_for_file(output_file, format)
    _extract(
        cli_state.sdk,
        cli_state.profile,
        cli_state.search_filters,
        begin,
        end,
        advanced_query,
        incremental,
        output_logger,
    )


@alerts.command()
@server_options
@alert_options
@search_options
@global_options
def send_to(
    cli_state, format, hostname, protocol, begin, end, advanced_query, incremental, **kwargs
):
    output_logger = logger_factory.get_logger_for_server(hostname, protocol, format)
    _extract(
        cli_state.sdk,
        cli_state.profile,
        cli_state.search_filters,
        begin,
        end,
        advanced_query,
        incremental,
        output_logger,
    )


def _extract(sdk, profile, filter_list, begin, end, advanced_query, incremental, output_logger):
    store = AlertCursorStore(profile.name) if incremental else None
    handlers = create_handlers(sdk, AlertExtractor, output_logger, store)
    extractor = AlertExtractor(sdk, handlers)
    if advanced_query:
        extractor.extract_advanced(advanced_query)
    else:
        if begin or end:
            filter_list.append(create_time_range_filter(DateObserved, begin, end))
        extractor.extract(*filter_list)
    if handlers.TOTAL_EVENTS == 0 and not errors.ERRORED:
        logger.print_info(u"No results found.")
