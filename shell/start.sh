#!/bin/bash
SHELL_PATH=$(dirname $(readlink -f "$0"))
main_file="main.py"
cmd="cd ${SHELL_PATH}/../src;python ${main_file}"
session_name="jd-qg"
session=$(tmux ls|grep ${session_name})
if [ -n "$session" ]; then
	echo "正在停止服务：${session_name}"
    tmux kill-session -t ${session_name}
    sleep 3
fi
echo "启动会话： ${session_name}"
tmux new -s ${session_name} -d
tmux send -t ${session_name} "${cmd}" Enter
echo "启动完成"
