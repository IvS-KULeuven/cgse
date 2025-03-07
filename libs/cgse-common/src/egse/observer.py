"""
This module implements a standard Observer <-> Observable pattern.

!!! Bug
    The methods in the Observable are not PEP8 compliant and need to be deprecated and changed.
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

    def addObserver(self, observer):
        if observer not in self.observers:
            self.observers.append(observer)

    def deleteObserver(self, observer):
        self.observers.remove(observer)

    def clearObservers(self):
        self.observers = []

    def countObservers(self):
        return len(self.observers)

    def notifyObservers(self, changedObject):
        # FIXME: put a try..except here to log any problem that occurred in the observer's update()
        #        method
        for observer in self.observers:
            observer.update(changedObject)

    def actionObservers(self, actions):
        # FIXME: put a try..except here to log any problem that occurred in the observer's do()
        #        method
        for observer in self.observers:
            observer.do(actions)
