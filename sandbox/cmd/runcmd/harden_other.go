//go:build !linux

// bash-dash local modification (not upstream); see harden_linux.go.
package main

func hardenPID1() {}
