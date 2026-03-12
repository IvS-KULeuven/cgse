import textwrap

import rich

from egse.confman import ConfigurationManagerProxy
from egse.confman import is_configuration_manager_active
from egse.log import logger
from egse.response import Failure
from egse.setup import Setup


class CoreSetupProvider:
    def load_setup(self, setup_id: int = None, **kwargs) -> Setup | None:
        """
        This function loads the Setup corresponding with the given `setup_id`.

        Loading a Setup means:

        * that this Setup will also be loaded and activated in the configuration manager,
        * that this Setup will be available from the `GlobalState.setup`

        When no setup_id is provided, the current Setup is loaded from the configuration manager.

        When `from_disk` is True, the Setup will not be loaded from the configuration manager, but it
        will be loaded from disk. No interaction with the configuration manager happens in this case.

        Args:
            setup_id (int): the identifier for the Setup
            site_id (str): the name of the test house

        Returns:
            The requested Setup or None when the Setup could not be loaded from the \
            configuration manager.

        """
        logger.info(f"Loading Setup from core services, {setup_id=}, {kwargs=}")

        if not is_configuration_manager_active():
            logger.warning(
                textwrap.dedent(
                    """\
                    Could not reach the Configuration Manager to request the Setup.
    
                    Check if the Configuration Manager is running and why it can not be consulted. When it's
                    back on-line, do a 'load_setup()'.
                    """
                )
            )

            return None

        with ConfigurationManagerProxy() as proxy:
            setup = proxy.load_setup(setup_id) if setup_id else proxy.get_setup()
            if setup:
                logger.info(f"Loaded Setup {setup.get_id()}")
            return setup

    def submit_setup(self, setup: Setup, description: str, **kwargs) -> str | None:
        """
        Submit the given Setup to the Configuration Manager.

        When you submit a Setup, the Configuration Manager will save this Setup with the
        next (new) setup id and make this Setup the current Setup in the Configuration manager
        unless you have explicitly set `replace=False` in which case the current Setup will
        not be replaced with the new Setup.

        Args:
            setup (Setup): a (new) Setup to submit to the configuration manager
            description (str): one-liner to help identifying the Setup afterwards

        Returns:
            The Setup ID of the newly created Setup or None.
        """
        # We have not yet decided if this option should be made available. Therefore, we
        # leave it here as hardcoded True.

        # replace (bool): True if the current Setup in the configuration manager shall
        #                 be replaced by this new Setup. [default=True]
        replace: bool = True

        logger.info(f"Submitting Setup to core services, {setup=}, {description=}, {kwargs=}")

        if not is_configuration_manager_active():
            logger.warning(
                textwrap.dedent(
                    """\
                    Could not reach the Configuration Manager to submit the Setup.
    
                    Check if the Configuration Manager is running and why it can not be consulted. When it's
                    back on-line, redo the 'submit_setup()'.
                    """
                )
            )

            return None

        try:
            with ConfigurationManagerProxy() as proxy:
                setup = proxy.submit_setup(setup, description, replace)

            if setup is None:
                rich.print("[red]Submit failed for given Setup, no reason given.[/red]")
            elif isinstance(setup, Failure):
                rich.print(f"[red]Submit failed for given Setup[/red]: {setup}")
                setup = None
            elif replace:
                rich.print(
                    textwrap.dedent(
                        """\
                        [green]
                        Your new setup has been submitted and pushed to GitHub. The new setup is also
                        activated in the configuration manager. Load the new setup in your session with:
    
                            setup = load_setup()
                        [/]
                        """
                    )
                )
            else:
                rich.print(
                    textwrap.dedent(
                        f"""[dark_orange]
                        Your new setup has been submitted and pushed to GitHub, but has not been
                        activated in the configuration manager. To activate this setup, use the
                        following command:
    
                            setup = load_setup({str(setup.get_id())})
                        [/]
                        """
                    )
                )

            return setup.get_id() if setup is not None else None

        except ConnectionError:
            rich.print("Could not make a connection with the Configuration Manager, no Setup was submitted.")
        except NotImplementedError:
            rich.print(
                textwrap.dedent(
                    """\
                    Caught a NotImplementedError. That usually means the configuration manager is not running or
                    can not be reached. Check on the egse-server if the `cm_cs` process is running. If not you will
                    need to be restart the core services.
                    """
                )
            )

    def list_setups(**attr) -> None:
        logger.warning("Loading extension: list_setups() from cgse-core")

        return None

    def can_handle(self, source: str) -> bool:
        return source == "core-services"
