import httplib2
from sre_constants import error as sre_error

from django.utils import timezone

from celery.task import task
from google_analytics.utils import heal_headers

# in 4.1, we could use autoretry_for=(Exception,), retry_backoff=True
@task(bind=True, ignore_result=True, default_retry_delay=5)
def send_tracking(self, params, x_forwarded_for=None, timestamp=None):
    url = params.get('url')
    user_agent = params.get('user_agent')
    language = params.get('language')
    body = params.get('body')
    request_method = params.get('request_method')

    request_kwargs = {
        'headers': {
            'User-Agent': user_agent,
        }
    }
    if language:
        request_kwargs['headers']['Accept-Language'] = language
    if x_forwarded_for:
        request_kwargs['headers']['X-Forwarded-For'] = x_forwarded_for

    # if this is a UA event, add
    # the queue time parameter
    if timestamp and body:
        diff = timezone.now() - timestamp
        body = "%s&qt=%d" % (body, int(diff.total_seconds() * 1000))

    if request_method not in ('GET', 'HEAD') and body:
        request_kwargs['body'] = body

    # send the request
    http = httplib2.Http()

    try:
        try:
            try:
                resp, content = http.request(
                    url, request_method,
                    **request_kwargs
                )
            except sre_error:
                heal_headers(request_kwargs['headers'])
                resp, content = http.request(
                    url, request_method,
                    **request_kwargs
                )
        except httplib2.HttpLib2Error as e:
            raise Exception("%s | '%s'" % (e, url))
    except Exception as exc:
        # Sept 2017: getting occassional bursts of failures
        raise self.retry(exc=exc, max_retries=20)
