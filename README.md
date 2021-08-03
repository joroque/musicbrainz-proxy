# Code Exercise for Backend Engineer

## Constraints

- Following "best practices" is not the main focus.
- Application in single Python module.
- `requests` and `hug` as the only third-party libraries to handle HTTP stuff.
- No Django or any of the most popular frameworks. Nothing against them, it's
just they're overkill in this case and I would end up with more boilerplate
code than anything else.
- No database or persistence layer, for simplicity.

## Installation

### Docker

```shell
$ docker run --rm -ti -p 9999:8000 musicbrainz-proxy
```

This will publish the container's port 8000 (development web server)
to port 9999 on the Docker host.

To access the endpoint from your terminal run:

```bash
curl --request GET \
--url 'http://192.168.122.239:9999/albums/?mbid=f6beac20-5dfe-4d1f-ae02-0b0a740aafd6&offset=4&limit=37'
```