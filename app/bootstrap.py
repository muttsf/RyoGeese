"""Early startup failure reporting without per-launch debug folders."""
import sys
sys.dont_write_bytecode=True
if __name__=='__main__':
    try:
        from launch import main
        main()
    except Exception as exc:
        import traceback
        try:
            from log_files import default_logs,local_time
            logs=default_logs()
            logs.write('报错',dict(时间=local_time(),kind='BOOTSTRAP_ERROR',traceback=traceback.format_exc()[-8192:]))
            logs.close()
        except Exception:pass
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,str(exc),'RyoGeese未能打开',0x10)
