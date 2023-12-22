from shutil import rmtree
from os import getcwd, path
from argparse import ArgumentParser
from datetime import datetime
from pathlib import Path

from _pytest.capture import CaptureFixture
from _pytest.tmpdir import TempPathFactory
from pytest_mock import MockerFixture

from grizzly_cli.run import run, create_parser
from grizzly_cli.utils import setup_logging

from ..helpers import onerror, CaseInsensitive

CWD = getcwd()


def test_run(capsys: CaptureFixture, mocker: MockerFixture, tmp_path_factory: TempPathFactory) -> None:
    setup_logging()

    original_tmp_path = tmp_path_factory._basetemp
    tmp_path_factory._basetemp = Path.cwd() / '.pytest_tmp'
    test_context = tmp_path_factory.mktemp('test_context')
    execution_context = test_context / 'execution-context'
    execution_context.mkdir()
    mount_context = test_context / 'mount-context'
    mount_context.mkdir()
    (execution_context / 'test.feature').write_text('Feature: this feature is testing something')
    (execution_context / 'configuration.yaml').write_text('configuration:')

    parser = ArgumentParser()

    sub_parsers = parser.add_subparsers(dest='test')

    create_parser(sub_parsers, parent='local')

    try:
        mocker.patch('grizzly_cli.run.grizzly_cli.EXECUTION_CONTEXT', str(execution_context))
        mocker.patch('grizzly_cli.run.grizzly_cli.MOUNT_CONTEXT', str(mount_context))
        mocker.patch('grizzly_cli.run.get_hostname', return_value='localhost')
        mocker.patch('grizzly_cli.run.find_variable_names_in_questions', side_effect=[['foo', 'bar'], [], [], [], [], [], []])
        mocker.patch('grizzly_cli.run.find_metadata_notices', side_effect=[[], ['is the event log cleared?'], ['hello world', 'foo bar'], [], [], [], []])
        mocker.patch('grizzly_cli.run.distribution_of_users_per_scenario', autospec=True)
        ask_yes_no_mock = mocker.patch('grizzly_cli.run.ask_yes_no', autospec=True)
        distributed_mock = mocker.MagicMock(return_value=0)
        local_mock = mocker.MagicMock(return_value=0)
        get_input_mock = mocker.patch('grizzly_cli.run.get_input', side_effect=['bar', 'foo'])

        setattr(getattr(run, '__wrapped__'), '__value__', str(execution_context))

        arguments = parser.parse_args([
            'run',
            '-e', f'{execution_context}/configuration.yaml',
            f'{execution_context}/test.feature',
        ])
        setattr(arguments, 'verbose', True)
        setattr(arguments, 'file', ' '.join(arguments.file))

        assert run(arguments, distributed_mock) == 0

        capture = capsys.readouterr()
        assert capture.out == ''
        assert capture.err == '''feature file requires values for 2 variables
the following values was provided:
foo = bar
bar = foo
'''

        local_mock.assert_not_called()
        distributed_mock.assert_called_once_with(
            arguments,
            {
                'GRIZZLY_CLI_HOST': 'localhost',
                'GRIZZLY_EXECUTION_CONTEXT': str(execution_context),
                'GRIZZLY_MOUNT_CONTEXT': str(mount_context),
                'GRIZZLY_CONFIGURATION_FILE': CaseInsensitive(path.join(execution_context, 'configuration.yaml')),
                'TESTDATA_VARIABLE_foo': 'bar',
                'TESTDATA_VARIABLE_bar': 'foo',
            }, {
                'master': [],
                'worker': [],
                'common': ['--stop', '--verbose', '--no-logcapture', '--no-capture', '--no-capture-stderr'],
            }
        )
        distributed_mock.reset_mock()

        ask_yes_no_mock.assert_called_once_with('continue?')
        ask_yes_no_mock.reset_mock()
        assert get_input_mock.call_count == 2
        args, kwargs = get_input_mock.call_args_list[0]
        assert kwargs == {}
        assert args[0] == 'initial value for "foo": '
        args, kwargs = get_input_mock.call_args_list[1]
        assert kwargs == {}
        assert args[0] == 'initial value for "bar": '
        get_input_mock.reset_mock()

        assert capture.out == ''
        assert capture.err == (
            'feature file requires values for 2 variables\n'
            'the following values was provided:\n'
            'foo = bar\n'
            'bar = foo\n'
        )

        arguments = parser.parse_args([
            'run',
            '-e', f'{execution_context}/configuration.yaml',
            f'{execution_context}/test.feature',
        ])
        setattr(arguments, 'file', ' '.join(arguments.file))

        assert run(arguments, local_mock) == 0

        capture = capsys.readouterr()

        distributed_mock.assert_not_called()
        local_mock.assert_called_once_with(
            arguments,
            {
                'GRIZZLY_CLI_HOST': 'localhost',
                'GRIZZLY_EXECUTION_CONTEXT': str(execution_context),
                'GRIZZLY_MOUNT_CONTEXT': str(mount_context),
                'GRIZZLY_CONFIGURATION_FILE': CaseInsensitive(path.join(execution_context, 'configuration.yaml')),
            }, {
                'master': [],
                'worker': [],
                'common': ['--stop'],
            }
        )
        local_mock.reset_mock()

        ask_yes_no_mock.assert_called_once_with('is the event log cleared?')
        ask_yes_no_mock.reset_mock()
        get_input_mock.assert_not_called()

        assert capture.err == ''
        assert capture.out == ''

        # with --yes, notices should only be printed, and not needed to be confirmed via ask_yes_no
        arguments = parser.parse_args([
            'run',
            '-e', f'{execution_context}/configuration.yaml',
            '--yes',
            f'{execution_context}/test.feature',
        ])
        setattr(arguments, 'file', ' '.join(arguments.file))

        assert run(arguments, local_mock) == 0

        distributed_mock.assert_not_called()

        local_mock.assert_called_once_with(
            arguments,
            {
                'GRIZZLY_CLI_HOST': 'localhost',
                'GRIZZLY_EXECUTION_CONTEXT': str(execution_context),
                'GRIZZLY_MOUNT_CONTEXT': str(mount_context),
                'GRIZZLY_CONFIGURATION_FILE': CaseInsensitive(path.join(execution_context, 'configuration.yaml')),
            }, {
                'master': [],
                'worker': [],
                'common': ['--stop'],
            }
        )
        local_mock.reset_mock()

        ask_yes_no_mock.assert_not_called()
        get_input_mock.assert_not_called()

        assert capture.err == ''
        assert capture.out == ''

        # no `csv_prefix` nothing should be added
        arguments = parser.parse_args([
            'run',
            '-e', f'{execution_context}/configuration.yaml',
            '--yes',
            f'{execution_context}/test.feature',
        ])
        setattr(arguments, 'file', ' '.join(arguments.file))
        setattr(arguments, 'csv_interval', 20)

        assert run(arguments, local_mock) == 0

        local_mock.assert_called_once_with(
            arguments,
            {
                'GRIZZLY_CLI_HOST': 'localhost',
                'GRIZZLY_EXECUTION_CONTEXT': str(execution_context),
                'GRIZZLY_MOUNT_CONTEXT': str(mount_context),
                'GRIZZLY_CONFIGURATION_FILE': CaseInsensitive(path.join(execution_context, 'configuration.yaml')),
            }, {
                'master': [],
                'worker': [],
                'common': ['--stop'],
            }
        )
        local_mock.reset_mock()
        distributed_mock.assert_not_called()

        # static csv-prefix
        arguments = parser.parse_args([
            'run',
            '-e', f'{execution_context}/configuration.yaml',
            '--yes',
            f'{execution_context}/test.feature',
        ])
        setattr(arguments, 'file', ' '.join(arguments.file))
        setattr(arguments, 'csv_interval', 20)
        setattr(arguments, 'csv_prefix', 'test test')

        assert run(arguments, local_mock) == 0

        distributed_mock.assert_not_called()
        local_mock.assert_called_once_with(
            arguments,
            {
                'GRIZZLY_CLI_HOST': 'localhost',
                'GRIZZLY_EXECUTION_CONTEXT': str(execution_context),
                'GRIZZLY_MOUNT_CONTEXT': str(mount_context),
                'GRIZZLY_CONFIGURATION_FILE': CaseInsensitive(path.join(execution_context, 'configuration.yaml')),
            }, {
                'master': [],
                'worker': [],
                'common': ['--stop', '-Dcsv-prefix="test test"', '-Dcsv-interval=20'],
            }
        )
        local_mock.reset_mock()

        # dynamic csv-prefix
        datetime_mock = mocker.patch(
            'grizzly_cli.run.datetime',
            side_effect=lambda *args, **kwargs: datetime(*args, **kwargs)
        )
        datetime_mock.now.return_value = datetime(2022, 12, 6, 13, 1, 13)
        arguments = parser.parse_args([
            'run',
            '-e', f'{execution_context}/configuration.yaml',
            '--yes',
            f'{execution_context}/test.feature',
        ])
        setattr(arguments, 'file', ' '.join(arguments.file))
        setattr(arguments, 'csv_prefix', True)
        setattr(arguments, 'csv_interval', 20)
        setattr(arguments, 'csv_flush_interval', 60)

        assert run(arguments, distributed_mock) == 0

        local_mock.assert_not_called()
        distributed_mock.assert_called_once_with(
            arguments,
            {
                'GRIZZLY_CLI_HOST': 'localhost',
                'GRIZZLY_EXECUTION_CONTEXT': str(execution_context),
                'GRIZZLY_MOUNT_CONTEXT': str(mount_context),
                'GRIZZLY_CONFIGURATION_FILE': CaseInsensitive(path.join(execution_context, 'configuration.yaml')),
            }, {
                'master': [],
                'worker': [],
                'common': ['--stop', '-Dcsv-prefix="this_feature_is_testing_something_20221206T130113"', '-Dcsv-interval=20', '-Dcsv-flush-interval=60'],
            }
        )
        distributed_mock.reset_mock()

        setattr(arguments, 'csv_prefix', None)
        setattr(arguments, 'csv_flush_interval', None)

        # --log-dir
        arguments = parser.parse_args([
            'run',
            '-e', f'{execution_context}/configuration.yaml',
            '--yes',
            f'{execution_context}/test.feature',
        ])
        setattr(arguments, 'file', ' '.join(arguments.file))
        setattr(arguments, 'log_dir', 'foobar')

        assert run(arguments, distributed_mock) == 0

        args, kwargs = distributed_mock.call_args_list[-1]
        assert kwargs == {}
        assert args[0] is arguments
        assert args[1].get('GRIZZLY_LOG_DIR', None) == 'foobar'
    finally:
        tmp_path_factory._basetemp = original_tmp_path
        rmtree(test_context, onerror=onerror)
