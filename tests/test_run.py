from shutil import rmtree
from os import getcwd, environ, path
from tempfile import gettempdir
from argparse import ArgumentParser

from _pytest.capture import CaptureFixture
from _pytest.tmpdir import TempPathFactory
from pytest_mock import MockerFixture

from grizzly_cli.run import distributed, local, run, create_parser

from .helpers import onerror

CWD = getcwd()


def test_distributed(capsys: CaptureFixture, mocker: MockerFixture, tmp_path_factory: TempPathFactory) -> None:
    test_context = tmp_path_factory.mktemp('test_context')
    (test_context / 'test.feature').write_text('Feature:')

    mocker.patch('grizzly_cli.run.getuser', side_effect=['test-user'] * 5)
    mocker.patch('grizzly_cli.run.get_default_mtu', side_effect=['1500', None, '1400', '1330', '1800'])
    mocker.patch('grizzly_cli.run.build', side_effect=[255, 0, 0])
    mocker.patch('grizzly_cli.run.list_images', side_effect=[{}, {}, {}, {'grizzly-cli-test-project': {'test-user': {}}}, {'grizzly-cli-test-project': {'test-user': {}}}])

    import grizzly_cli.run
    mocker.patch.object(grizzly_cli.run, 'EXECUTION_CONTEXT', '/tmp/execution-context')
    mocker.patch.object(grizzly_cli.run, 'STATIC_CONTEXT', '/tmp/static-context')
    mocker.patch.object(grizzly_cli.run, 'MOUNT_CONTEXT', '/tmp/mount-context')
    mocker.patch.object(grizzly_cli.run, 'PROJECT_NAME', 'grizzly-cli-test-project')

    mocker.patch('grizzly_cli.run.is_docker_compose_v2', return_value=False)

    run_command_mock = mocker.patch('grizzly_cli.run.run_command', side_effect=[111, 0, 0, 1, 0, 0, 1, 0, 13])

    parser = ArgumentParser()

    sub_parsers = parser.add_subparsers(dest='test')

    create_parser(sub_parsers)

    try:
        arguments = parser.parse_args(['run', 'dist', f'{test_context}/test.feature', '--workers', '3', '--tty'])
        setattr(arguments, 'container_system', 'docker')

        # this is set in the devcontainer
        for key in environ.keys():
            if key.startswith('GRIZZLY_'):
                del environ[key]

        assert distributed(arguments, {}, {}) == 111
        capture = capsys.readouterr()
        import sys
        assert capture.err == ''
        assert capture.out == (
            '!! something in the compose project is not valid, check with:\n'
            f'grizzly-cli {" ".join(sys.argv[1:])} --validate-config\n'
        )

        try:
            del environ['GRIZZLY_MTU']
        except KeyError:
            pass

        assert distributed(arguments, {}, {}) == 255
        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == (
            '!! unable to determine MTU, try manually setting GRIZZLY_MTU environment variable if anything other than 1500 is needed\n'
            '!! failed to build grizzly-cli-test-project, rc=255\n'
        )
        assert environ.get('GRIZZLY_MTU', None) == '1500'
        assert environ.get('GRIZZLY_EXECUTION_CONTEXT', None) == '/tmp/execution-context'
        assert environ.get('GRIZZLY_STATIC_CONTEXT', None) == '/tmp/static-context'
        assert environ.get('GRIZZLY_MOUNT_CONTEXT', None) == '/tmp/mount-context'
        assert environ.get('GRIZZLY_PROJECT_NAME', None) == 'grizzly-cli-test-project'
        assert environ.get('GRIZZLY_USER_TAG', None) == 'test-user'
        assert environ.get('GRIZZLY_EXPECTED_WORKERS', None) == '3'
        assert environ.get('GRIZZLY_MASTER_RUN_ARGS', None) is None
        assert environ.get('GRIZZLY_WORKER_RUN_ARGS', None) is None
        assert environ.get('GRIZZLY_COMMON_RUN_ARGS', None) is None
        assert environ.get('GRIZZLY_IMAGE_REGISTRY', None) == ''
        assert environ.get('GRIZZLY_ENVIRONMENT_FILE', '').startswith(gettempdir())
        assert environ.get('GRIZZLY_LIMIT_NOFILE', None) == '10001'
        assert environ.get('GRIZZLY_HEALTH_CHECK_INTERVAL', None) == '5'
        assert environ.get('GRIZZLY_HEALTH_CHECK_TIMEOUT', None) == '3'
        assert environ.get('GRIZZLY_HEALTH_CHECK_RETRIES', None) == '3'
        assert environ.get('GRIZZLY_CONTAINER_TTY', None) == 'true'

        # this is set in the devcontainer
        for key in environ.keys():
            if key.startswith('GRIZZLY_'):
                del environ[key]

        arguments = parser.parse_args([
            'run', 'dist', f'{test_context}/test.feature',
            '--workers', '3',
            '--build',
            '--limit-nofile', '133700',
            '--health-interval', '10',
            '--health-timeout', '8',
            '--health-retries', '30',
            '--registry', 'gchr.io/biometria-se',
        ])
        setattr(arguments, 'container_system', 'docker')

        mocker.patch('grizzly_cli.run.is_docker_compose_v2', side_effect=[True, False])

        # docker-compose v2
        assert distributed(
            arguments,
            {
                'GRIZZLY_CONFIGURATION_FILE': '/tmp/execution-context/configuration.yaml',
                'GRIZZLY_TEST_VAR': 'True',
            },
            {
                'master': ['--foo', 'bar', '--master'],
                'worker': ['--bar', 'foo', '--worker'],
                'common': ['--common', 'true'],
            },
        ) == 1
        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == (
            '\n!! something went wrong, check container logs with:\n'
            'docker container logs grizzly-cli-test-project-test-user-master-1\n'
            'docker container logs grizzly-cli-test-project-test-user-worker-2\n'
            'docker container logs grizzly-cli-test-project-test-user-worker-3\n'
            'docker container logs grizzly-cli-test-project-test-user-worker-4\n'
        )

        assert run_command_mock.call_count == 5
        args, _ = run_command_mock.call_args_list[-3]
        assert args[0] == [
            'docker-compose',
            '-p', 'grizzly-cli-test-project-test-user',
            '-f', '/tmp/static-context/compose.yaml',
            'config',
        ]
        args, _ = run_command_mock.call_args_list[-2]
        assert args[0] == [
            'docker-compose',
            '-p', 'grizzly-cli-test-project-test-user',
            '-f', '/tmp/static-context/compose.yaml',
            'up',
            '--scale', 'worker=3',
            '--remove-orphans',
        ]
        args, _ = run_command_mock.call_args_list[-1]
        assert args[0] == [
            'docker-compose',
            '-p', 'grizzly-cli-test-project-test-user',
            '-f', '/tmp/static-context/compose.yaml',
            'stop',
        ]

        assert environ.get('GRIZZLY_RUN_FILE', None) == f'{test_context}/test.feature'
        assert environ.get('GRIZZLY_MTU', None) == '1400'
        assert environ.get('GRIZZLY_EXECUTION_CONTEXT', None) == '/tmp/execution-context'
        assert environ.get('GRIZZLY_STATIC_CONTEXT', None) == '/tmp/static-context'
        assert environ.get('GRIZZLY_MOUNT_CONTEXT', None) == '/tmp/mount-context'
        assert environ.get('GRIZZLY_PROJECT_NAME', None) == 'grizzly-cli-test-project'
        assert environ.get('GRIZZLY_USER_TAG', None) == 'test-user'
        assert environ.get('GRIZZLY_EXPECTED_WORKERS', None) == '3'
        assert environ.get('GRIZZLY_MASTER_RUN_ARGS', None) == '--foo bar --master'
        assert environ.get('GRIZZLY_WORKER_RUN_ARGS', None) == '--bar foo --worker'
        assert environ.get('GRIZZLY_COMMON_RUN_ARGS', None) == '--common true'
        assert environ.get('GRIZZLY_ENVIRONMENT_FILE', '').startswith(gettempdir())
        assert environ.get('GRIZZLY_LIMIT_NOFILE', None) == '133700'
        assert environ.get('GRIZZLY_HEALTH_CHECK_INTERVAL', None) == '10'
        assert environ.get('GRIZZLY_HEALTH_CHECK_TIMEOUT', None) == '8'
        assert environ.get('GRIZZLY_HEALTH_CHECK_RETRIES', None) == '30'
        assert environ.get('GRIZZLY_IMAGE_REGISTRY', None) == 'gchr.io/biometria-se'
        assert environ.get('GRIZZLY_CONTAINER_TTY', None) == 'false'

        # docker-compose v1
        assert distributed(
            arguments,
            {
                'GRIZZLY_CONFIGURATION_FILE': '/tmp/execution-context/configuration.yaml',
                'GRIZZLY_TEST_VAR': 'True',
            },
            {
                'master': ['--foo', 'bar', '--master'],
                'worker': ['--bar', 'foo', '--worker'],
                'common': ['--common', 'true'],
            },
        ) == 1
        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == (
            '\n!! something went wrong, check container logs with:\n'
            'docker container logs grizzly-cli-test-project-test-user_master_1\n'
            'docker container logs grizzly-cli-test-project-test-user_worker_1\n'
            'docker container logs grizzly-cli-test-project-test-user_worker_2\n'
            'docker container logs grizzly-cli-test-project-test-user_worker_3\n'
        )

        mocker.patch('grizzly_cli.run.is_docker_compose_v2', return_value=False)

        # this is set in the devcontainer
        for key in environ.keys():
            if key.startswith('GRIZZLY_'):
                del environ[key]

        arguments = parser.parse_args([
            'run', 'dist', f'{test_context}/test.feature',
            '--workers', '1',
            '--id', 'suffix',
            '--validate-config',
            '--limit-nofile', '20000',
            '--health-interval', '10',
            '--health-timeout', '8',
            '--health-retries', '30',
        ])
        setattr(arguments, 'container_system', 'docker')

        assert distributed(
            arguments,
            {
                'GRIZZLY_CONFIGURATION_FILE': '/tmp/execution-context/configuration.yaml',
                'GRIZZLY_TEST_VAR': 'True',
            },
            {
                'master': ['--foo', 'bar', '--master'],
                'worker': ['--bar', 'foo', '--worker'],
                'common': ['--common', 'true'],
            },
        ) == 13
        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == ''

        assert run_command_mock.call_count == 9
        args, _ = run_command_mock.call_args_list[-1]
        assert args[0] == [
            'docker-compose',
            '-p', 'grizzly-cli-test-project-suffix-test-user',
            '-f', '/tmp/static-context/compose.yaml',
            'config',
        ]

        assert environ.get('GRIZZLY_RUN_FILE', None) == f'{test_context}/test.feature'
        assert environ.get('GRIZZLY_MTU', None) == '1800'
        assert environ.get('GRIZZLY_EXECUTION_CONTEXT', None) == '/tmp/execution-context'
        assert environ.get('GRIZZLY_STATIC_CONTEXT', None) == '/tmp/static-context'
        assert environ.get('GRIZZLY_MOUNT_CONTEXT', None) == '/tmp/mount-context'
        assert environ.get('GRIZZLY_PROJECT_NAME', None) == 'grizzly-cli-test-project'
        assert environ.get('GRIZZLY_USER_TAG', None) == 'test-user'
        assert environ.get('GRIZZLY_EXPECTED_WORKERS', None) == '1'
        assert environ.get('GRIZZLY_MASTER_RUN_ARGS', None) == '--foo bar --master'
        assert environ.get('GRIZZLY_WORKER_RUN_ARGS', None) == '--bar foo --worker'
        assert environ.get('GRIZZLY_COMMON_RUN_ARGS', None) == '--common true'
        assert environ.get('GRIZZLY_ENVIRONMENT_FILE', '').startswith(gettempdir())
        assert environ.get('GRIZZLY_LIMIT_NOFILE', None) == '20000'
        assert environ.get('GRIZZLY_HEALTH_CHECK_INTERVAL', None) == '10'
        assert environ.get('GRIZZLY_HEALTH_CHECK_TIMEOUT', None) == '8'
        assert environ.get('GRIZZLY_HEALTH_CHECK_RETRIES', None) == '30'

    finally:
        rmtree(test_context, onerror=onerror)
        for key in environ.keys():
            if key.startswith('GRIZZLY_'):
                del environ[key]


def test_local(mocker: MockerFixture, tmp_path_factory: TempPathFactory) -> None:
    run_command = mocker.patch('grizzly_cli.run.run_command', side_effect=[0])
    test_context = tmp_path_factory.mktemp('test_context')
    (test_context / 'test.feature').write_text('Feature:')

    parser = ArgumentParser()

    sub_parsers = parser.add_subparsers(dest='test')

    create_parser(sub_parsers)

    try:
        assert environ.get('GRIZZLY_TEST_VAR', None) is None

        arguments = parser.parse_args([
            'run', 'local', f'{test_context}/test.feature',
        ])

        assert local(
            arguments,
            {
                'GRIZZLY_TEST_VAR': 'True',
            },
            {
                'master': ['--foo', 'bar', '--master'],
                'worker': ['--bar', 'foo', '--worker'],
                'common': ['--common', 'true'],
            },
        ) == 0

        assert run_command.call_count == 1
        args, _ = run_command.call_args_list[-1]
        assert args[0] == [
            'behave',
            f'{test_context}/test.feature',
            '--foo', 'bar', '--master',
            '--bar', 'foo', '--worker',
            '--common', 'true',
        ]

        assert environ.get('GRIZZLY_TEST_VAR', None) == 'True'
    finally:
        rmtree(test_context, onerror=onerror)
        try:
            del environ['GRIZZLY_TEST_VAR']
        except:
            pass


def test_run(capsys: CaptureFixture, mocker: MockerFixture, tmp_path_factory: TempPathFactory) -> None:
    test_context = tmp_path_factory.mktemp('test_context')
    execution_context = test_context / 'execution-context'
    execution_context.mkdir()
    mount_context = test_context / 'mount-context'
    mount_context.mkdir()
    (execution_context / 'test.feature').write_text('Feature:')
    (execution_context / 'configuration.yaml').write_text('configuration:')

    parser = ArgumentParser()

    sub_parsers = parser.add_subparsers(dest='test')

    create_parser(sub_parsers)

    try:
        mocker.patch('grizzly_cli.run.EXECUTION_CONTEXT', str(execution_context))
        mocker.patch('grizzly_cli.run.MOUNT_CONTEXT', str(mount_context))
        mocker.patch('grizzly_cli.run.get_hostname', side_effect=['localhost'] * 3)
        mocker.patch('grizzly_cli.run.find_variable_names_in_questions', side_effect=[['foo', 'bar'], []])
        mocker.patch('grizzly_cli.run.distribution_of_users_per_scenario', autospec=True)
        ask_yes_no_mock = mocker.patch('grizzly_cli.run.ask_yes_no', autospec=True)
        distributed_mock = mocker.patch('grizzly_cli.run.distributed', side_effect=[0])
        local_mock = mocker.patch('grizzly_cli.run.local', side_effect=[0])
        get_input_mock = mocker.patch('grizzly_cli.run.get_input', side_effect=['bar', 'foo'])

        setattr(getattr(run, '__wrapped__'), '__value__', str(execution_context))

        arguments = parser.parse_args([
            'run', '-e', f'{execution_context}/configuration.yaml',
            'dist', f'{execution_context}/test.feature',
        ])
        setattr(arguments, 'verbose', True)

        assert run(arguments) == 0

        capture = capsys.readouterr()
        assert capture.err == ''
        assert capture.out == '''!! created a default requirements.txt with one dependency:
grizzly-loadtester

feature file requires values for 2 variables
the following values was provided:
foo = bar
bar = foo
'''

        assert local_mock.call_count == 0
        assert distributed_mock.call_count == 1
        args, _ = distributed_mock.call_args_list[-1]

        assert args[0] is arguments

        # windows hack... one place uses C:\ and getcwd uses c:\
        args[1]['GRIZZLY_CONFIGURATION_FILE'] = args[1]['GRIZZLY_CONFIGURATION_FILE'].lower()
        assert args[1] == {
            'GRIZZLY_CLI_HOST': 'localhost',
            'GRIZZLY_EXECUTION_CONTEXT': str(execution_context),
            'GRIZZLY_MOUNT_CONTEXT': str(mount_context),
            'GRIZZLY_CONFIGURATION_FILE': path.join(execution_context, 'configuration.yaml').lower(),
            'TESTDATA_VARIABLE_foo': 'bar',
            'TESTDATA_VARIABLE_bar': 'foo',
        }
        assert args[2] == {
            'master': [],
            'worker': [],
            'common': ['--stop', '--verbose', '--no-logcapture', '--no-capture', '--no-capture-stderr'],
        }

        assert ask_yes_no_mock.call_count == 1
        assert get_input_mock.call_count == 2
        args, _ = get_input_mock.call_args_list[0]
        assert args[0] == 'initial value for "foo": '
        args, _ = get_input_mock.call_args_list[1]
        assert args[0] == 'initial value for "bar": '

        assert capture.err == ''
        assert capture.out == (
            '!! created a default requirements.txt with one dependency:\n'
            'grizzly-loadtester\n\n'
            'feature file requires values for 2 variables\n'
            'the following values was provided:\n'
            'foo = bar\n'
            'bar = foo\n'
        )

        arguments = parser.parse_args([
            'run', '-e', f'{execution_context}/configuration.yaml',
            'local', f'{execution_context}/test.feature',
        ])

        assert run(arguments) == 0

        capture = capsys.readouterr()

        assert local_mock.call_count == 1
        assert distributed_mock.call_count == 1
        args, _ = local_mock.call_args_list[-1]

        assert args[0] is arguments

        # windows hack... one place uses C:\ and getcwd uses c:\
        args[1]['GRIZZLY_CONFIGURATION_FILE'] = args[1]['GRIZZLY_CONFIGURATION_FILE'].lower()

        assert args[1] == {
            'GRIZZLY_CLI_HOST': 'localhost',
            'GRIZZLY_EXECUTION_CONTEXT': str(execution_context),
            'GRIZZLY_MOUNT_CONTEXT': str(mount_context),
            'GRIZZLY_CONFIGURATION_FILE': path.join(execution_context, 'configuration.yaml').lower(),
        }
        assert args[2] == {
            'master': [],
            'worker': [],
            'common': ['--stop'],
        }

        assert ask_yes_no_mock.call_count == 1
        assert get_input_mock.call_count == 2

        assert capture.err == ''
        assert capture.out == ''
    finally:
        rmtree(test_context, onerror=onerror)