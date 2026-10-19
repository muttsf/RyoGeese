"""Request shutdown; a failed UI path falls back to the same owned reader."""


def request_close(backend):
    try:
        backend.close()
        return ()
    except Exception as exc:
        errors=['停止读取异常：'+type(exc).__name__+': '+str(exc)[:200]]
        try:
            backend.abort()
        except Exception as abort_error:
            errors.append('强制收尾未完成：'+type(abort_error).__name__+': '+str(abort_error)[:200])
        return tuple(errors)
