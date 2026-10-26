set pagination off
set confirm off
set print thread-events off
set debuginfod enabled off
run
bt 50
thread apply all bt 5
info sharedlibrary libomni.ui
quit
