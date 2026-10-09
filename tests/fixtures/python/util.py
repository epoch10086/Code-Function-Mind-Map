def helper(value=1):
    """返回给定值。"""
    return value


class Worker:
    def __init__(self):
        self.value = 1

    def run(self):
        return helper(self.value)
