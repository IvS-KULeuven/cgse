# Using dotenv

The `cgse` command and subcommands make use of `dotenv`. The package loads environment variables from a `.env` file into
your application's environment (`os.environ`). The idea is to store sensitive data like API keys, database passwords, or
configuration settings in the `.env` file. This file stays local on your machine and is ignored by git making your
project more secure. At the start of an application, call `load_dotenv()` and then access variables using
`os.getenv('KEY')` throughout your code.

The typical workflow is: create a `.env` file with your environment variables in your project root or in your 
working directory, add `.env` to the `.gitignore`, commit a `.env.example` template (with dummy values) so other 
developers know what variables are needed, and call `load_dotenv()` at the top of your main entry point before 
accessing any environment variables. In production, you usually skip the `.env` file entirely and set real 
environment variables through your hosting platform.

!!! note 
    The `load_dotenv()` function will **not overwrite** existing environment variables in `os.environ`. This means
    environment variables already set in your shell or system take precedence over values in your `.env` file. 
    To override this behavior and force `.env` values to take priority, use `load_dotenv(override=True)`.

!!! Warning
    Since the CGSE is a package that is used by and installed by other packages, the CGSE command loads the `.env` from
    your current working directory instead of the location of the executing script. Otherwise, it would always look 
    into the folder where the `cgse.py` script is located and that is probably not what you want.

Below, we have summarised some basic know-hows for using dotenv:

- place the `.env` file at the root location of your project or in your current working directory. 
  When you are developing for the CGSE, use the top-level folder of the monorepo. Please note that 
  the `load_dotenv()` function searches for a `.env` file in the current folder, the parent folder 
  up until it hits your home directory.
- the format to use for the environment variables is `KEY=VALUE`.
- do not use quotes, unless the VALUE contains spaces.
- do not use the _`export`_ statement (the `.env` files are not shell scripts).
- add a comment after a hash character: '`#`'
- call the `load_dotenv()` function at the top of your entry point file or app, right after the imports.
- Call the `load_dotenv()` function only once at application startup, not in every module.
- You might want to consider calling `load_dotenv(find_dotenv(usecwd=True))` instead
- Do not call the function in library code.
