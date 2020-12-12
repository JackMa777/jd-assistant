#!/bin/bash
session_name="jd-qg"
session=$(tmux ls|grep ${session_name})
if [ -n "$session" ]
	then
		tmux kill-session -t ${session_name}
		echo "会话 ${session_name} 已关闭"
		sleep 2
	else
		echo "会话 ${session_name} 不存在"
fi

