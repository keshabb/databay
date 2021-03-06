import logging
import time
from threading import Thread
from unittest import TestCase
from unittest.mock import patch

import schedule

import databay
from databay import Link
from databay.errors import MissingLinkError
from databay.planners import SchedulePlanner
from databay.planners.schedule_planner import ScheduleIntervalError
from test_utils import fqname, DummyException, DummyUnusualException


class TestSchedulePlanner(TestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        logging.getLogger('databay').setLevel(logging.WARNING)


    @patch(fqname(Link), spec=Link)
    def setUp(self, link):
        self.planner = SchedulePlanner(refresh_interval=0.02)

        def set_job(job):
            link.job = job

        link.interval.total_seconds.return_value = 0.02
        link.set_job.side_effect = set_job
        link.job = None
        self.link = link


    def tearDown(self):
        if len(schedule.jobs) > 0:
            schedule.clear()

    def test__run_job(self):
        self.planner._create_thread_pool()
        self.planner._run_job(self.link)
        self.link.transfer.assert_called_once()
        self.planner._destroy_thread_pool()

    def test__schedule(self):
        self.planner._schedule(self.link)
        self.assertIsNotNone(self.link.job, 'Link should contain a job')
        schedule_job = schedule.jobs[0]
        self.assertEqual(self.link.job, schedule_job, 'Link\'s job should be same as schedule\'s')
        # self.planner._unschedule(link)

    def test__unschedule(self):
        self.planner._schedule(self.link)
        self.planner._unschedule(self.link)
        self.assertIsNone(self.link.job, 'Link should not contain a job')
        self.assertEqual(len(schedule.jobs), 0, 'Schedule should not have any jobs')

    def test__unschedule_invalid(self):
        self.planner._unschedule(self.link)
        self.assertIsNone(self.link.job, 'Link should not contain a job')
        self.assertEqual(len(schedule.jobs), 0, 'Scheduler should not have any jobs')

    def test_add_links(self):
        self.planner.add_links(self.link)
        self.assertIsNotNone(self.link.job, 'Link should contain a job')
        self.assertTrue(self.link in self.planner.links, 'Planner should contain the link')

    def test_add_links_on_init(self):
        self.planner = SchedulePlanner(self.link, refresh_interval=0.02)
        self.assertIsNotNone(self.link.job, 'Link should contain a job')
        self.assertTrue(self.link in self.planner.links, 'Planner should contain the link')

    def test_remove_links(self):
        self.planner.add_links(self.link)
        self.planner.remove_links(self.link)
        self.assertIsNone(self.link.job, 'Link should not contain a job')
        self.assertTrue(self.link not in self.planner.links, 'Planner should not contain the link')

    def test_remove_invalid_link(self):
        self.assertRaises(MissingLinkError, self.planner.remove_links, self.link)
        self.assertIsNone(self.link.job, 'Link should not contain a job')
        self.assertTrue(self.link not in self.planner.links, 'Planner should not contain the link')

    def test_start(self):
        th = Thread(target=self.planner.start, daemon=True)
        th.start()
        self.assertTrue(self.planner._running, 'Planner should be running')
        self.planner.shutdown()
        th.join(timeout=2)
        self.assertFalse(th.is_alive(), 'Thread should be stopped.')

    def test_shutdown(self):
        th = Thread(target=self.planner.start, daemon=True)
        th.start()
        self.planner.shutdown()
        self.assertFalse(self.planner._running, 'Planner should be not running')
        self.assertIsNone(self.planner._thread_pool, 'Planner should not have a thread pool')
        th.join(timeout=2)
        self.assertFalse(th.is_alive(), 'Thread should be stopped.')

    def test_add_and_run(self):
        self.link.interval.total_seconds.return_value = 0.02
        self.planner._refresh_interval = 0.02
        self.planner.add_links(self.link)

        th = Thread(target=self.planner.start, daemon=True)
        th.start()
        time.sleep(0.04)
        self.link.transfer.assert_called()

        self.planner.shutdown()
        th.join(timeout=2)
        self.assertFalse(th.is_alive(), 'Thread should be stopped.')

    def test_invalid_interval(self):
        self.link.interval.total_seconds.return_value = 0.1
        self.planner._refresh_interval = 0.2

        self.assertRaises(ScheduleIntervalError, self.planner.add_links, self.link)

    def _with_exception(self, link, catch_exceptions):
        logging.getLogger('databay').setLevel(logging.CRITICAL)
        self.planner = SchedulePlanner(catch_exceptions=catch_exceptions)
        link.transfer.side_effect = DummyException()
        link.interval.total_seconds.return_value = 0.02
        self.planner._refresh_interval = 0.02

        link.transfer.side_effect = DummyException()
        link.interval.total_seconds.return_value = 0.02
        self.planner.add_links(link)

        th = Thread(target=self.planner.start, daemon=True)
        th.start()
        time.sleep(0.04)
        link.transfer.assert_called()

        if catch_exceptions:
            self.assertTrue(self.planner.running, 'Scheduler should be running')
            self.planner.shutdown(False)
            th.join(timeout=2)
            self.assertFalse(th.is_alive(), 'Thread should be stopped.')

        self.assertFalse(self.planner.running, 'Scheduler should be stopped')

    def test_catch_exception(self):
        self._with_exception(self.link, True)

    def test_raise_exception(self):
        self._with_exception(self.link, False)

    def test_uncommon_exception(self):
        logging.getLogger('databay').setLevel(logging.CRITICAL)

        self.link.transfer.side_effect = DummyUnusualException(argA=123, argB=True)
        self.link.interval.total_seconds.return_value = 0.02
        self.planner.add_links(self.link)

        th = Thread(target=self.planner.start, daemon=True)
        th.start()
        time.sleep(0.04)
        self.link.transfer.assert_called()

        self.assertFalse(self.planner.running, 'Scheduler should be stopped')