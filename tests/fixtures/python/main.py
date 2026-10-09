from util import helper as renamed, Worker


def callback():
    return renamed()


def recurse(n):
    if n:
        return recurse(n - 1)
    return renamed()


def main(register):
    worker = Worker()
    worker.run()
    register(callback)
    getattr(worker, 'dynamic')()
    return recurse(1)
