#!/bin/bash
session_name="jd-qg"
session=$(tmux ls|grep ${session_name})
if [ -n "$session" ]
	then
		tmux send -t ${session_name} "echo \"Exit: [Ctrl+b,Enter d] or [tmux detach]\"" Enter
		tmux send -t ${session_name} "echo \"Close: [tmux kill-session -t ${session_name}]\"" Enter
		tmux attach -t ${session_name}
		echo "已进入 ${session_name} 会话"
	else
		echo "会话 ${session_name} 不存在"
fi