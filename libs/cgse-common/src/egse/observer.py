"""
This module implements a standard Observer <-> Observable pattern.
"""

import abc


class Observer(abc.ABC):
    """The observer that needs to take action when notified."""

    @abc.abstractmethod
    def update(self, changed_object):
        pass

    @abc.abstractmethod
    def do(self, actions):
        pass


class Observable:
    """The object that sends out notifications to the observers."""

    def __init__(self):
        self.observers = []

    def add_observer(self, observer):
        if observer not in self.observers:
            self.observers.append(observer)

    def delete_observer(self, observer):
        self.observers.remove(observer)

    def clear_observers(self):
        self.observers = []

    def count_observers(self):
        return len(self.observers)

    def notify_observers(self, changed_object):
        # FIXME: put a try..except here to log any problem that occurred in the observer's update()
        #        method
        for observer in self.observers:
            observer.update(changed_object)

    def action_observers(self, actions):
        # FIXME: put a try..except here to log any problem that occurred in the observer's do()
        #        method
        for observer in self.observers:
            observer.do(actions)
