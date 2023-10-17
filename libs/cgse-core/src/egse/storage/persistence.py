"""
This module handles the persistence storage for the Common-EGSE.
"""
import csv
import logging
import re
import sqlite3
from pathlib import Path
from sqlite3 import Connection
from typing import Optional
from typing import Union

from egse.plugin import load_plugins
from egse.storage import PersistenceLayer
from egse.system import read_last_line

logger = logging.getLogger(__name__)


def parts(data, delimiter=",", quote_char='"', keep_quote_char=False):
    compos = []
    part = ''
    skip = False
    for character in data:
        if (
            character == delimiter
            and skip
            or character not in [delimiter, quote_char]
        ):
            part += character
        elif character == delimiter:
            compos.append(part)
            part = ''
        else:
            skip = not skip
            if keep_quote_char: part += character
    if part:
        compos.append(part)

    return compos


# TODO:
#  it might be useful to remember the last 10 or 100 lines and have a dedicated read
#  function that returns these line quickly without the need to open the file.


class CSV1(PersistenceLayer):
    """A Persistence Layer that saves data in a CSV file.

    This class uses a custom implementation.
    """

    extension = "csv"

    def __init__(self, filename, prep: dict = None):
        """
        The `prep` argument is a dictionary that contains information to initialise this
        persistence layer. The CSV uses the following:

        * column_names: a list or tuple with the names of the column headers
        * mode: the mode in which the file shall be opened

        Args:
            filename: a str or Path that represents the name of the file
            prep (dict): preparation information to initialise the persistence layer
        """
        prep = prep or {}
        self._filepath = Path(filename)
        self._column_names = prep.get("column_names") or []
        self._mode = prep.get("mode") or "r"
        self._quote_char = prep.get("quote_char") or "|"
        self._delimiter = prep.get("delimiter") or ","
        self._fd = None
        self._regex = re.compile(rf"\\.|[{re.escape(self._quote_char)}{re.escape(self._delimiter)}']", re.DOTALL)

    def is_open(self):
        # we don't want to expose the file descriptor
        return bool(self._fd)

    def open(self, mode=None):
        """Opens the CSV file and writes the header if column_names are provided."""
        self._mode = mode or self._mode
        logger.debug(f"Opening file {self._filepath} in mode '{self._mode}'")
        self._fd = self._filepath.open(mode=self._mode)
        if self._column_names and self._mode == "w":
            self._fd.write(",".join(self._column_names))
            self._fd.write("\n")
        return self

    def close(self):
        logger.debug(f"Closing file {self._filepath}")
        self._fd.close()
        self._fd = None

    def exists(self):
        return self._filepath.exists()

    def __enter__(self):
        # Only open the file when not opened before. Remember if the file was open.
        self._context_fd = self._fd
        return self if self._fd else self.open(mode=self._mode)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # only close the file if it was opened by the context manager
        self._context_fd or self.close()
        # propagate any exception to the caller, i.e. don't return True
        # return True

    def create(self, data):
        """Write a line in the CSV file with the given numbers separated by commas.

        The `data` argument can be a list or a tuple in which case the numbers are just joined
        to form a comma separated line. The `data` argument can also be a `dict`, in which
        case the column_names are used to order the values from the dictionary.
        The keys in the dictionary shall match the entries in the column_names.

        Args:
            data: the input data to create the line
        Raises:
            IOError when the CSV file was not opened before.
        """

        def quote(value):
            if self._delimiter in value:
                return f"{self._quote_char}{value}{self._quote_char}"
            else:
                return value

        if self._fd:
            if isinstance(data, (list, tuple)):

                data = self._delimiter.join([quote(str(x)) for x in data])

            elif isinstance(data, dict):

                if not self._column_names:
                    logger.error("Cannot write ordered dictionary data, no column names provided.")
                    return

                # Extract the values from the dictionary and sort them according to the column_names

                data_list = [(k, v) for k, v in data.items()]
                sorted_data_list = sorted(data_list, key=lambda x: self._column_names.index(x[0]))
                data = self._delimiter.join([quote(str(x[1])) for x in sorted_data_list])

            self._fd.write(data)
            data.endswith("\n") or self._fd.write("\n")
            self._fd.flush()
        else:
            raise IOError(
                "You try to write to a file which has not been opened yet, "
                "first call the open method or use the context manager."
            )

    def read(self, select=None):
        def generator_function():
            while True:
                line = self._fd.readline().rstrip()
                if line:
                    yield parts(line, self._delimiter, self._quote_char)
                else:
                    break

        return generator_function()

    def update(self, line_no, data):
        logger.warning("The update functionality is not implemented for the CSV persistence layer.")

    def delete(self, line_no):
        logger.warning("The delete functionality is not implemented for the CSV persistence layer.")

    def get_filepath(self):
        return self._filepath


class CSV2(PersistenceLayer):
    """A Persistence Layer that saves data in a CSV file."""

    extension = "csv"

    def __init__(self, filename, prep: dict = None):
        """
        The `prep` argument is a dictionary that contains information to initialise this
        persistence layer. The CSV initialisation uses the following:

        * column_names: a list or tuple with the names of the column headers
        * mode: the mode in which the file shall be opened

        Args:
            filename: a str or Path that represents the name of the file
            prep (dict): preparation information to initialise the persistence layer
        """
        prep = prep or {}
        self._filepath = Path(filename)
        self._column_names = prep.get("column_names") or []
        self._mode = prep.get("mode") or "r"
        self._quote_char = prep.get("quote_char") or "|"
        self._delimiter = prep.get("delimiter") or ","
        self._fd = None

    def __enter__(self):
        self._context_fd = self._fd
        return self if self._fd else self.open(mode=self._mode)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # only close the file if it was opened by the context manager
        self._context_fd or self.close()
        # propagate any exception to the caller, i.e. don't return True
        # return True

    def exists(self):
        return self._filepath.exists()

    def is_open(self):
        # we don't want to expose the file descriptor
        return bool(self._fd)

    def open(self, mode=None):
        """Opens the CSV file and writes the header if column_names are provided."""
        self._mode = mode or self._mode
        logger.debug(f"Opening file {self._filepath} in mode '{self._mode}'")
        self._fd = self._filepath.open(mode=self._mode)
        if self._column_names and self._mode == "w":
            writer = csv.DictWriter(self._fd, fieldnames=self._column_names)
            writer.writeheader()
        return self

    def close(self):
        logger.debug(f"Closing file {self._filepath}")
        self._fd.close()
        self._fd = None

    def create(self, data):
        """Write a line in the CSV file.

        The `data` argument can be a list or a tuple in which case the numbers are just joined
        to form a comma separated line. The `data` argument can also be a `dict`, in which
        case the column_names is used to order the values from the dictionary.
        The keys in the dictionary shall match the entries in the column_names, but if there are
        extra keys in the dictionary, they will be silently ignored.

        Args:
            data: the input data to create the line
        Raises:
            IOError when the CSV file was not opened before.
        """
        if not self._fd:
            raise IOError(
                "You try to write to a file which has not been opened yet, "
                "first call the open method or use the context manager."
            )
        if isinstance(data, (list, tuple)):
            writer = csv.writer(
                self._fd,
                delimiter=self._delimiter,
                quotechar=self._quote_char, quoting=csv.QUOTE_MINIMAL,
            )
            writer.writerow(data)
        elif isinstance(data, dict):
            if not self._column_names:
                logger.error("Cannot write ordered dictionary data, no column names provided.")
                return

            writer = csv.DictWriter(
                self._fd,
                fieldnames=self._column_names, extrasaction="ignore",
                delimiter=self._delimiter,
                quotechar=self._quote_char, quoting=csv.QUOTE_MINIMAL,
            )
            writer.writerow(data)
        else:
            self._fd.write(data)
            data.endswith("\n") or self._fd.write("\n")

        self._fd.flush()

    def read(self, select=None):
        csv_reader = csv.reader(self._fd, delimiter=self._delimiter, quotechar=self._quote_char)

        def generator_function():
            if self._column_names:
                yield next(csv_reader)

            for line in csv_reader:
                yield line

        return generator_function()

    def update(self, line_no, data):
        logger.warning("The update functionality is not implemented for the CSV persistence layer.")

    def delete(self, line_no):
        logger.warning("The delete functionality is not implemented for the CSV persistence layer.")

    def get_filepath(self):
        return self._filepath


class TXT(PersistenceLayer):

    extension = "txt"

    def __init__(self, filename, prep: dict = None):
        """
        The `prep` argument is a dictionary that contains information to initialise this
        persistence layer. The TXT initialisation uses the following:

        * mode: the mode in which the file shall be opened
        * ending: a character sequence that is used to end the write action
        * header: a header text that will be written when opening the file

        Args:
            filename: a str or Path that represents the name of the file
            prep (dict): preparation information to initialise the persistence layer
        """
        prep = prep or {}
        self._filepath = Path(filename)
        self._mode = prep.get("mode") or "r"
        self._ending = prep.get("ending") or ""
        self._header = prep.get("header") or ""
        self._fd = None

    def open(self, mode=None):
        """Opens the TXT file."""
        self._mode = mode or self._mode
        logger.debug(f"Opening file {self._filepath} in mode '{self._mode}'")
        self._fd = self._filepath.open(mode=self._mode)
        if self._header and self._mode == "w":
            self.create(self._header)
        return self

    def close(self):
        logger.debug(f"Closing file {self._filepath}")
        self._fd.close()
        self._fd = None

    def exists(self):
        return self._filepath.exists()

    def __enter__(self):
        self._context_fd = self._fd
        return self if self._fd else self.open(mode=self._mode)

    def __exit__(self, exc_type, exc_val, exc_tb):
        # only close the file if it was opened by the context manager
        self._context_fd or self.close()
        return True

    def create(self, data):
        data_str = str(data)
        logger.log(5, f"Writing data: {data_str[:min(80, len(data_str))]}...")
        if self._fd:
            self._fd.write(str(data))
            self._fd.write(self._ending)
            self._fd.flush()
        else:
            raise IOError(
                "You try to write to a file which has not been opened yet, "
                "first call the open method or use the context manager."
            )

    def read(self, select=None):
        """Read lines form the file.

        The `select` argument can take the following values:

        * `select == "last_line"`: return the last line of the file as a string
        * `select == ("contains", <string>)`: returns all the files that contain `<string>`
        * `select == ("startswith", <string>)`: return all line that start with `<string>`

        Args:
            select (str or dict): defines a selection / filter for reading the lines
        Returns:
            A list of lines from the file or the last line as a string.
        """
        if select == "last_line":
            return read_last_line(self._filepath, max_line_length=4096)

        result = []

        if isinstance(select, tuple):
            if select[0] == "contains":
                with self._filepath.open(mode="r") as fd:
                    for line in fd:
                        if select[1] in line:
                            result.append(line.rstrip())
            elif select[0] == "startswith":
                with self._filepath.open(mode="r") as fd:
                    for line in fd:
                        if line.startswith(select[1]):
                            result.append(line.rstrip())
            return result

        with self._filepath.open("r") as fd:
            result = [line.rstrip() for line in fd]

        return result

    def update(self, idx, data):
        logger.warning("The update functionality is not implemented for the TXT persistence layer.")

    def delete(self, idx):
        logger.warning("The delete functionality is not implemented for the TXT persistence layer.")

    def get_filepath(self):
        return self._filepath


class SQLite(PersistenceLayer):

    extension = "sqlite3"

    def __init__(self, filename: Union[str, Path], prep: dict = None):
        self._filepath = Path(filename).with_suffix(f".{self.extension}")
        self._prep = prep
        self._connection: Optional[Connection] = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self, mode=None):
        self._connection = sqlite3.connect(self._filepath)

    def close(self):
        self._connection.close()

    def exists(self):
        return self._filepath.exists()

    def _execute(self, statement, values=None):
        with self._connection:
            cursor = self._connection.cursor()
            cursor.execute(statement, values or [])
            return cursor

    def create_table(self, table_name, columns):
        columns_with_types = [
            f'{column_name} {data_type}'
            for column_name, data_type in columns.items()
        ]
        self._execute(
            f"""CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(columns_with_types)});"""
        )

    def drop_table(self, table_name):
        self._execute(f"DROP TABLE {table_name};")

    def add_to_table(self, table_name, data):
        placeholders = ', '.join('?' * len(data))
        column_names = ', '.join(data.keys())
        column_values = tuple(data.values())

        self._execute(
            f"""INSERT INTO {table_name} ({column_names}) VALUES ({placeholders}); """,
            column_values,
        )

    def select_from_table(self, table_name: str, criteria: dict = None, order_by=None):
        criteria = criteria or {}

        query = f"SELECT * FROM {table_name}"

        if criteria:
            placeholders = [f'{column} = ?' for column in criteria.keys()]
            select_criteria = ' AND '.join(placeholders)
            query += f' WHERE {select_criteria}'

        if order_by:
            query += f' ORDER BY {order_by}'

        return self._execute(
            query,
            tuple(criteria.values()),
        )

    def delete_from_table(self, table_name, criteria):
        placeholders = [f'{column} = ?' for column in criteria.keys()]
        delete_criteria = ' AND '.join(placeholders)

        self._execute(
            f"""DELETE FROM {table_name} WHERE {delete_criteria}; """, tuple(criteria.values()),
        )

    def update_table(self, table_name, criteria, data):
        update_placeholders = [f'{column} = ?' for column in criteria.keys()]
        update_criteria = ' AND '.join(update_placeholders)
        data_placeholders = ', '.join(f'{key} = ?' for key in data.keys())

        values = tuple(data.values()) + tuple(criteria.values())

        self._execute(
            f"""UPDATE {table_name} SET {data_placeholders} WHERE {update_criteria};""",
            values,
        )

    def create(self, data):
        # Should call add_to_table()
        pass

    def read(self, select=None):
        # Should call select_from_table()
        pass

    def update(self, idx, data):
        # Should call update_table()
        pass

    def delete(self, idx):
        # Should call delete_from_table
        pass

    def get_filepath(self):
        return self._filepath


CSV = CSV2

# Since we use pluggable types of persistence classes, we make them available in a dictionary TYPES.
# The classes defined in this module are added manually, the classes provided by other packages are
# loaded from their entry points and added to TYPES.

TYPES = {
    'CSV': CSV2,
    'CSV1': CSV1,
    'CSV2': CSV2,
    'SQL': SQLite,
    'TXT': TXT,
}

for name, ep in load_plugins(entry_point="cgse.storage.persistence").items():
    if ep is not None:
        TYPES[name] = ep
