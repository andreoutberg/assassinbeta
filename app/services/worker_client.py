"""
Worker Client - Interface for enqueueing grid search tasks

Provides a clean interface for the main FastAPI process to enqueue
CPU-intensive grid search tasks to worker processes.

USAGE:
    from app.services.worker_client import WorkerClient

    # Enqueue grid search task
    job = await WorkerClient.enqueue_grid_search(
        trade_id=123,
        symbol='BTCUSDT',
        direction='long',
        webhook_source='tradingview'
    )

    # Check job status
    status = await WorkerClient.get_job_status(job.id)

    # Get job result (blocking until complete)
    result = await WorkerClient.get_job_result(job.id, timeout=30)
"""
import os
import logging
from typing import Dict, Any, Optional
from rq import Queue
from rq.job import Job
import redis

logger = logging.getLogger(__name__)

# Redis connection configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))

# Queue name
GRID_SEARCH_QUEUE = 'grid_search'


class WorkerClient:
    """Client for enqueueing and monitoring worker tasks"""

    _redis_conn: Optional[redis.Redis] = None
    _queue: Optional[Queue] = None

    @classmethod
    def _get_connection(cls) -> redis.Redis:
        """Get or create Redis connection"""
        if cls._redis_conn is None:
            cls._redis_conn = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=False  # RQ requires binary mode
            )
            logger.info(f"📡 [WORKER_CLIENT] Connected to Redis at {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
        return cls._redis_conn

    @classmethod
    def _get_queue(cls) -> Queue:
        """Get or create RQ Queue"""
        if cls._queue is None:
            conn = cls._get_connection()
            cls._queue = Queue(GRID_SEARCH_QUEUE, connection=conn)
            logger.info(f"📋 [WORKER_CLIENT] Connected to queue '{GRID_SEARCH_QUEUE}'")
        return cls._queue

    @classmethod
    async def enqueue_grid_search(
        cls,
        trade_id: int,
        symbol: str,
        direction: str,
        webhook_source: str,
        timeout: int = 300  # 5 minutes max
    ) -> Job:
        """
        Enqueue a grid search task to worker process

        Args:
            trade_id: ID of completed baseline trade
            symbol: Trading pair (e.g., 'BTCUSDT')
            direction: 'long' or 'short'
            webhook_source: Signal source
            timeout: Max execution time in seconds (default 300s = 5min)

        Returns:
            RQ Job object with job.id for tracking

        Example:
            job = await WorkerClient.enqueue_grid_search(
                trade_id=123,
                symbol='BTCUSDT',
                direction='long',
                webhook_source='tradingview'
            )
            logger.info(f"Job enqueued: {job.id}")
        """
        try:
            queue = cls._get_queue()

            # Import worker function
            from worker import run_grid_search_task

            # Enqueue job with positional args for function, kwargs for RQ options
            job = queue.enqueue(
                run_grid_search_task,
                trade_id,  # Positional argument
                symbol,  # Positional argument
                direction,  # Positional argument
                webhook_source,  # Positional argument
                job_timeout=timeout,  # RQ option
                result_ttl=3600,  # RQ option: Keep result for 1 hour
                failure_ttl=3600  # RQ option: Keep failure info for 1 hour
            )

            logger.info(
                f"✅ [WORKER_CLIENT] Enqueued grid search job {job.id} for trade {trade_id}: "
                f"{symbol} {direction} via {webhook_source}"
            )

            return job

        except Exception as e:
            logger.error(
                f"❌ [WORKER_CLIENT] Failed to enqueue grid search for trade {trade_id}: {e}",
                exc_info=True
            )
            raise

    @classmethod
    async def get_job_status(cls, job_id: str) -> Dict[str, Any]:
        """
        Get status of an enqueued job

        Args:
            job_id: RQ job ID

        Returns:
            Dict with status info:
                - status: 'queued', 'started', 'finished', 'failed'
                - enqueued_at: timestamp
                - started_at: timestamp (if started)
                - ended_at: timestamp (if finished/failed)
                - result: job result (if finished)
                - exc_info: error info (if failed)

        Example:
            status = await WorkerClient.get_job_status(job_id)
            if status['status'] == 'finished':
                print(status['result'])
        """
        try:
            conn = cls._get_connection()
            job = Job.fetch(job_id, connection=conn)

            status = {
                'job_id': job.id,
                'status': job.get_status(),
                'enqueued_at': job.enqueued_at.isoformat() if job.enqueued_at else None,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'ended_at': job.ended_at.isoformat() if job.ended_at else None,
            }

            # Add result if finished
            if job.is_finished:
                status['result'] = job.result

            # Add error info if failed
            if job.is_failed:
                status['exc_info'] = job.exc_info

            return status

        except Exception as e:
            logger.error(f"❌ [WORKER_CLIENT] Failed to get job status for {job_id}: {e}")
            return {
                'job_id': job_id,
                'status': 'unknown',
                'error': str(e)
            }

    @classmethod
    async def get_job_result(
        cls,
        job_id: str,
        timeout: int = 30
    ) -> Optional[Dict[str, Any]]:
        """
        Get result of job, blocking until complete (with timeout)

        Args:
            job_id: RQ job ID
            timeout: Max seconds to wait for result

        Returns:
            Job result dict or None if timeout/failed

        Example:
            result = await WorkerClient.get_job_result(job_id, timeout=30)
            if result and result['success']:
                print(f"Generated {result['strategies_generated']} strategies")
        """
        try:
            conn = cls._get_connection()
            job = Job.fetch(job_id, connection=conn)

            # Wait for result (blocking with timeout)
            result = job.return_value(timeout=timeout)

            if result:
                logger.info(f"✅ [WORKER_CLIENT] Job {job_id} completed: {result.get('success', False)}")
            else:
                logger.warning(f"⚠️ [WORKER_CLIENT] Job {job_id} returned no result")

            return result

        except Exception as e:
            logger.error(f"❌ [WORKER_CLIENT] Failed to get result for job {job_id}: {e}")
            return None

    @classmethod
    async def cancel_job(cls, job_id: str) -> bool:
        """
        Cancel a queued or running job

        Args:
            job_id: RQ job ID

        Returns:
            True if cancelled, False otherwise
        """
        try:
            conn = cls._get_connection()
            job = Job.fetch(job_id, connection=conn)

            if job.is_queued or job.is_started:
                job.cancel()
                logger.info(f"🛑 [WORKER_CLIENT] Cancelled job {job_id}")
                return True
            else:
                logger.warning(f"⚠️ [WORKER_CLIENT] Cannot cancel job {job_id} (status: {job.get_status()})")
                return False

        except Exception as e:
            logger.error(f"❌ [WORKER_CLIENT] Failed to cancel job {job_id}: {e}")
            return False

    @classmethod
    async def get_queue_info(cls) -> Dict[str, Any]:
        """
        Get information about the worker queue

        Returns:
            Dict with queue stats:
                - queue_name: str
                - queued_jobs: int
                - started_jobs: int
                - finished_jobs: int
                - failed_jobs: int

        Example:
            info = await WorkerClient.get_queue_info()
            print(f"Queue has {info['queued_jobs']} pending jobs")
        """
        try:
            queue = cls._get_queue()

            return {
                'queue_name': queue.name,
                'queued_jobs': len(queue),
                'started_jobs': queue.started_job_registry.count,
                'finished_jobs': queue.finished_job_registry.count,
                'failed_jobs': queue.failed_job_registry.count,
            }

        except Exception as e:
            logger.error(f"❌ [WORKER_CLIENT] Failed to get queue info: {e}")
            return {
                'queue_name': GRID_SEARCH_QUEUE,
                'error': str(e)
            }
