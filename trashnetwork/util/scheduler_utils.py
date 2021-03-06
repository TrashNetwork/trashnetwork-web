import datetime
import json

import pytz
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.job import Job
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.util import undefined

from trashnetwork import settings
from trashnetwork.util import mqtt_broker_utils

scheduler = None


def init_scheduler():
    global scheduler
    jobstores = {
        'default': RedisJobStore(db=settings.TN_SCHEDULER['REDIS_DB'])
    }
    executors = {
        'default': ThreadPoolExecutor(settings.TN_SCHEDULER['THREAD_POOL_SIZE']),
        'processpool': ProcessPoolExecutor(5)
    }
    job_defaults = {
        'coalesce': False,
        'max_instances': settings.TN_SCHEDULER['MAX_JOB_INSTANCE']
    }
    scheduler = BackgroundScheduler(jobstores=jobstores, executors=executors, job_defaults=job_defaults,
                                    timezone=pytz.timezone(settings.TIME_ZONE))
    scheduler.start()
    print('Scheduler is running...')


def stop_scheduler():
    global scheduler
    scheduler.shutdown(wait=False)
    print('Scheduler has stopped.')


def add_interval_job(job_id: str, job_func, minutes: int, start_time: datetime = undefined, args: list = None):
    scheduler.add_job(job_func, trigger='interval', minutes=int(minutes),
                      id=str(job_id), replace_existing=True, args=args,
                      next_run_time=start_time)


def is_job_scheduled(job_id: str):
    global scheduler
    return not scheduler.get_job(job_id) is None


def remove_job(job_id: str):
    global scheduler
    scheduler.remove_job(job_id)


JOB_CLEANING_REMINDER_PREFIX = 'cleaning_reminder/trash_'


def add_cleaning_reminder(trash_id: int):
    add_interval_job(job_id=JOB_CLEANING_REMINDER_PREFIX + str(trash_id),
                     job_func=job_cleaning_reminder,
                     minutes=settings.TN_CLEANING_REMINDER['INTERVAL_MINUTES'],
                     args=[trash_id])


def job_cleaning_reminder(trash_id: int):
    now = datetime.datetime.now()
    if now.isoweekday() < settings.TN_CLEANING_REMINDER['TIME_RANGE_START_WEEKDAY'] or \
                    now.isoweekday() > settings.TN_CLEANING_REMINDER['TIME_RANGE_END_WEEKDAY']:
        return
    if now.hour < settings.TN_CLEANING_REMINDER['TIME_RANGE_START_HOUR'] or \
                    now.hour > settings.TN_CLEANING_REMINDER['TIME_RANGE_END_HOUR']:
        return
    mqtt_broker_utils.publish_message(full_topic=settings.MQTT_TOPIC_CLEANING_REMINDER,
                                      message=json.dumps(
                                          {'trash_id': int(trash_id),
                                           'remind_time': int(now.timestamp())}
                                      ),
                                      qos=1)
