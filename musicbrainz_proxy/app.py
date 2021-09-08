import os

import hug
from redis import Redis
from rq import Queue
from rq.job import Job

from musicbrainz_proxy.client import MusicBrainzClient

redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
redis_port = os.environ.get("REDIS_PORT", 6379)
redis_conn = Redis(host=redis_host, port=redis_port)
job_queue = Queue(connection=redis_conn)

client = MusicBrainzClient()


@hug.local()
@hug.cli()
@hug.get(examples="mbid=65f4f0c5-ef9e-490c-aee3-909e7ae6b2ab&offset=0&limit25")
def albums(request, mbid: hug.types.text, limit: int = 50, offset: int = 0):
    """HTTP API endpoint that returns an artist's release groups.

    In MusicBrainz's terminology a 'release group' is what's more commonly known
    as 'album'. A 'release' is an instance of a 'release group' you can buy as
    CD, vinyl, etc.
    """
    # TODO: Pass `limit` and `offset`  to async function to know which data should be returned?
    job = job_queue.enqueue(client.get_aggregated_releases, mbid, result_ttl=500)
    return {"result_url": f"{request.scheme}://{request.netloc}/albums/result/{job.id}"}


@hug.local()
@hug.cli()
@hug.get("/albums/result/{job_id}/")
def result(job_id: hug.types.text):
    # TODO: Handle 404!
    job = Job.fetch(job_id, connection=redis_conn)

    # Get pagination from job args, apply pagination
    # paginated_response = job.result[offset : offset + limit]
    return {"albums": job.result}


if __name__ == "__main__":
    albums.interface.cli()
