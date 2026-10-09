package main
import "example.local/demo/util"
type Worker struct{}
func (w *Worker) Run() int { return util.Help() }
func main() { w:=Worker{}; w.Run(); util.Help() }
