# Style Guide

This part of the developer guide contains instructions for coding styles that are adopted for this project.

The style guide that we use for this project is [PEP8](https://www.python.org/dev/peps/pep-0008/). This is the standard for Python code and all IDEs, parsers and code formatters understand and work with this standard. PEP8 leaves room for project specific styles. A good style guide that we can follow is the [Google Style Guide](https://google.github.io/styleguide/pyguide.html).

The following sections will give the most used conventions with a few examples of good and bad.

## TL;DR

| Type | Style | Example |
|------|-------|---------|
| Classes | CapWords | ProcessManager, ImageViewer, CommandList, Observation, MetaData |
| Methods & Functions | lowercase with underscores | get_value, set_mask, create_image |
| Variables | lowercase with underscores | key, last_value, model, index, user_info |
| Constants | UPPERCASE with underscores | MAX_LINES, BLACK, COMMANDING_PORT |
| Modules & packages | lowercase **no** underscores | dataset, commanding, multiprocessing |

## General

* Name the class or variable or function with what it is, what it does or what it contains. A variable named `user_list` might look good at first, but what if at some point you want to change the list to a set so it can not contain duplicates. Are you going to rename everything into `user_set` or would `user_info` be a better name?
* Never use dashes in any name, they will raise a `SyntaxError: invalid syntax`.
* We introduce a number of relaxations to not break backward compatibility for the sake of a naming convention. As described in [A Foolish Consistency is the Hobgoblin of Little Minds](https://legacy.python.org/dev/peps/pep-0008/#a-foolish-consistency-is-the-hobgoblin-of-little-minds): _Consistency with this style guide is important. Consistency within a project is more important. Consistency within one module or function is the most important. [...] do not break backwards compatibility just to comply with this PEP!_

## Classes

Always use CamelCase (Python uses CapWords) for class names. When using acronyms, keep them all UPPER case.

* Class names should be nouns, like Observation
* Make sure to name classes distinctively
* Stick to one word for a concept when naming classes, i.e. words like `Manager` or `Controller` or `Organizer` all mean similar things. Choose one word for the concept and stick to it.
* If a word is already part of a package or module, don't use the same word in the class name again.

Good names are: `Observation`, `CalibrationFile`, `MetaData`, `Message`, `ReferenceFrame`, `URLParser`.

## Methods and Functions

A function or a method does something (and should only do one thing, SRP=Single Responsibility Principle), it is an action, so the name should reflect that action.

Always use lowercase words separated with underscores.

Good names are: `get_time_in_ms()`, `get_commanding_port()`, `is_connected()`, `parse_time()`, `setup_mask()`.

When working with legacy code or code from another project, names may be in camelCase (with the first letter a lower case letter). So we can in this case use also `getCommandPort()` or `isConnected()` as method and function names.

## Variables

Use the same naming convention as functions and methods, i.e. lowercase with underscores.

Good names are: `key`, `value`, `user_info`, `model`, `last_value`

Bad names: `NSegments`, `outNoise`

Take care not to use builtins: `list`, `type`, `filter`, `lambda`, `map`, `dict`, ...

Private variables (for classes) start with an underscore: `_name` or `_total_n_args`.

In the same spirit as method and function names, the variables can also be in camelCase for specific cases.

## CONSTANTS

Use ALL_UPPER_CASE with underscores for constants. Use constants always within a name space, not globally.

Good names: `MAX_LINES`, `BLACK`, `YELLOW`, `ESL_LINK_MODE_DISABLED`

## Modules and Packages

Use simple words for modules, preferably just one word like `datasets` or `commanding` or `storage` or `extensions`. If two words are unavoidable, just concatenate them, like `multiprocessing` or `sampledata` or `testdata`. If needed for readability, use an underscore to separate the words, e.g. `image_analysis`.

## Import Statements

* Group and sort import statements
* Never use the form `from <module> import *`
* Always use absolute imports in scripts

Be careful that you do not name any modules the same as a module in the Python standard library. This can result in strange effects and may result in an `AttributeError`. Suppose you have named a module `math` in the `egse` directory and it is imported and used further in the code as follows:

```python
from egse import math

# in some expression further down the code you might use

math.exp(a)
```

This will result in the following runtime error:

```text
File "some_module.py", line 8, in <module>
  print(math.exp(a))
AttributeError: module 'egse.math' has no attribute 'exp'
```

Of course this is an obvious example, but it might be more obscure like e.g. in this [GitHub issue](https://github.com/ParmEd/ParmEd/issues/148): 'module' 
object has no attribute 'Cmd'.
