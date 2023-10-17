from abc import ABC
from abc import abstractmethod


class PersistenceLayer(ABC):
    """The Persistence Layer implements the CRUD paradigm for storing data."""

    extension = "no_ext"
    """The file extension to use for this persistence type."""

    @abstractmethod
    def open(self, mode=None):
        """Opens the resource."""
        raise NotImplementedError("Persistence layers must implement the open method")

    @abstractmethod
    def close(self):
        """Closes the resource."""
        raise NotImplementedError("Persistence layers must implement the close method")

    @abstractmethod
    def exists(self):
        """Does the resource exists."""
        raise NotImplementedError("Persistence layers must implement the exists method")

    @abstractmethod
    def create(self, data):
        """Creates an entry in the persistence store."""
        raise NotImplementedError("Persistence layers must implement a create method")

    @abstractmethod
    def read(self, select=None):
        """Returns a list of all entries in the persistence store.

        The list can be filtered based on a selection from the `select` argument which
        should be a Callable object.

        Args:
            select (Callable): a filter function to narrow down the list of all entries.
        Returns:
            A list or generator for all entries in the persistence store.
        """
        raise NotImplementedError("Persistence layers must implement a read method")

    @abstractmethod
    def update(self, idx, data):
        """Updates the entry for index `idx` in the persistence store."""
        raise NotImplementedError("Persistence layers must implement an update method")

    @abstractmethod
    def delete(self, idx):
        """Deletes the entry for index `idx` from the persistence store."""
        raise NotImplementedError("Persistence layers must implement a delete method")

    @abstractmethod
    def get_filepath(self):
        """If this persistence class is file based, return its file path, otherwise return None."""
        raise NotImplementedError("Persistence layers must implement a get_filepath method")
