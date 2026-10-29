from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "spaced_positions.core"
    label = "core"

    def ready(self):
        from django.core.signals import got_request_exception

        from .usage import server_error

        got_request_exception.connect(server_error, dispatch_uid="usage-server-error")  # the usage report counts them
