from dash import callback_context, exceptions


def callback_prevent_initial_output(func):
    def wrapper(*args, **kwargs):
        if not callback_context.triggered:
            raise exceptions.PreventUpdate

        trigger = callback_context.triggered[0]
        if trigger["value"] is None:
            raise exceptions.PreventUpdate

        return func(*args, **kwargs)

    return wrapper
