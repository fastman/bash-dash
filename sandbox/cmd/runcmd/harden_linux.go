//go:build linux

// bash-dash local modification (not upstream): runcmd runs as PID 1 of the
// sandbox container with the same uid as the player's command.
package main

import (
	"os"
	"os/signal"
	"syscall"
)

// hardenPID1 stops the player's command (same uid) from tampering with runcmd:
//   - PR_SET_DUMPABLE=0 makes /proc/1/{fd,environ,mem,...} root-owned, so the
//     player cannot write to runcmd's stdout via /proc/1/fd/1 and forge a verdict.
//     Children reset to dumpable on execve, so bash is unaffected.
//   - Installing handlers (never drained; sends are dropped) means the kernel
//     delivers and discards these signals instead of killing PID 1. Handled
//     signals, unlike ignored ones, reset to default in the exec'd bash.
func hardenPID1() {
	if _, _, errno := syscall.RawSyscall(syscall.SYS_PRCTL, syscall.PR_SET_DUMPABLE, 0, 0); errno != 0 {
		os.Exit(70)
	}
	signal.Notify(make(chan os.Signal, 1),
		syscall.SIGTERM, syscall.SIGINT, syscall.SIGHUP,
		syscall.SIGQUIT, syscall.SIGUSR1, syscall.SIGUSR2)
}
