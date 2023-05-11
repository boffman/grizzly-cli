from os import environ
from tempfile import NamedTemporaryFile
from argparse import Namespace as Arguments
from getpass import getuser
from shutil import get_terminal_size

from ..argparse import ArgumentSubParser
from ..utils import run_command
from .. import PROJECT_NAME, STATIC_CONTEXT


def create_parser(sub_parser: ArgumentSubParser) -> None:
    # grizzly-cli dist clean ...
    clean_parser = sub_parser.add_parser('clean', description=(
        'clean all grizzly compose project resources; containers, images, networks and volumes'
    ),)

    clean_parser.add_argument(
        '--no-images',
        dest='images',
        action='store_false',
        required=False,
        default=True,
        help='do not remove images',
    )

    clean_parser.add_argument(
        '--no-networks',
        dest='networks',
        action='store_false',
        required=False,
        default=True,
        help='do not remove networks',
    )

    if clean_parser.prog != 'grizzly-cli dist clean':  # pragma: no cover
        clean_parser.prog = 'grizzly-cli dist clean'


def clean(args: Arguments) -> int:
    suffix = '' if args.id is None else f'-{args.id}'
    tag = getuser()

    if args.project_name is not None:
        project_name = args.project_name
    else:
        project_name = PROJECT_NAME

    columns, lines = get_terminal_size()
    env = environ.copy()

    with NamedTemporaryFile() as fd:
        env.update({
            'GRIZZLY_PROJECT_NAME': project_name,
            'GRIZZLY_USER_TAG': tag,
            'GRIZZLY_CONTAINER_TTY': 'false',
            'GRIZZLY_LIMIT_NOFILE': '1024',
            'GRIZZLY_ENVIRONMENT_FILE': fd.name,
            'COLUMNS': str(columns),
            'LINES': str(lines),
        })

        compose_command = [
            args.container_system, 'compose',
            '-f', f'{STATIC_CONTEXT}/compose.yaml',
            '-p', f'{project_name}{suffix}-{tag}',
            'rm', '-f', '-s', '-v',
        ]

        result = run_command(compose_command, env=env)

    if args.images:
        command = [
            args.container_system,
            'image', 'rm', f'{project_name}:{tag}'
        ]

        run_command(command)

    if args.networks:
        command = [
            args.container_system,
            'network', 'rm', f'{project_name}{suffix}-{tag}_default',
        ]

        run_command(command)

    return result.return_code
