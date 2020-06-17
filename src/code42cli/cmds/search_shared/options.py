import click

from code42cli.options import incompatible_with
from code42cli.date_helper import parse_min_timestamp, parse_max_timestamp
from code42cli.cmds.search_shared.enums import ServerProtocol
from code42cli.errors import DateArgumentError


def is_in_filter(filter_cls):
    def callback(ctx, arg):
        if arg:
            ctx.obj.search_filters.append(filter_cls.is_in(arg))
        return arg

    return callback


def not_in_filter(filter_cls):
    def callback(ctx, arg):
        if arg:
            ctx.obj.search_filters.append(filter_cls.not_in(arg))
        return arg

    return callback


def exists_filter(filter_cls):
    def callback(ctx, arg):
        if arg:
            ctx.obj.search_filters.append(filter_cls.exists())
            return arg

    return callback


def contains_filter(filter_cls):
    def callback(ctx, arg):
        if arg:
            for item in arg:
                ctx.obj.search_filters.append(filter_cls.contains(item))
        return arg

    return callback


def not_contains_filter(filter_cls):
    def callback(ctx, arg):
        if arg:
            for item in arg:
                ctx.obj.search_filters.append(filter_cls.not_contains(item))
        return arg

    return callback


AdvancedQueryIncompatible = incompatible_with("advanced_query")


def create_search_options(search_term):
    begin_option = click.option(
        "-b",
        "--begin",
        callback=lambda ctx, arg: parse_min_timestamp(arg),
        cls=AdvancedQueryIncompatible,
        help="The beginning of the date range in which to look for {}, can be a date/time in "
        "yyyy-MM-dd (UTC) or yyyy-MM-dd HH:MM:SS (UTC+24-hr time) format where the 'time' "
        "portion of the string can be partial (e.g. '2020-01-01 12' or '2020-01-01 01:15') "
        "or a short value representing days (30d), hours (24h) or minutes (15m) from current "
        "time.".format(search_term),
    )
    end_option = click.option(
        "-e",
        "--end",
        callback=lambda ctx, arg: parse_max_timestamp(arg),
        cls=AdvancedQueryIncompatible,
        help="The end of the date range in which to look for {}, argument format options are "
        "the same as --begin.".format(search_term),
    )
    advanced_query_option = click.option(
        "--advanced-query",
        help="\b\nA raw JSON {} query. "
        "Useful for when the provided query parameters do not satisfy your requirements."
        "\nWARNING: Using advanced queries is incompatible with other query-building args.".format(
            search_term
        ),
    )
    incremental_option = click.option(
        "-i",
        "--incremental",
        is_flag=True,
        cls=AdvancedQueryIncompatible,
        help="Only get {0} that were not previously retrieved.".format(search_term),
    )

    def search_options(f):
        f = begin_option(f)
        f = end_option(f)
        f = incremental_option(f)
        f = advanced_query_option(f)
        return f

    return search_options


output_file_arg = click.argument(
    "output_file", type=click.Path(dir_okay=False, resolve_path=True, writable=True)
)


def server_options(f):
    hostname_arg = click.argument("hostname")
    protocol_option = click.option(
        "-p",
        "--protocol",
        type=click.Choice(ServerProtocol()),
        default=ServerProtocol.UDP,
        help="Protocol used to send logs to server.",
    )
    f = hostname_arg(f)
    f = protocol_option(f)
    return f
