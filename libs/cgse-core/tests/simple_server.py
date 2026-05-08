import asyncio
import signal

from egse.env import bool_env
from egse.log import logging
from egse.system import type_name

logger = logging.getLogger("egse.test.async_stream_server")

VERBOSE_DEBUG = bool_env("VERBOSE_DEBUG")

SEPARATOR = b"\x03"


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info("peername")
    logger.info(f"Client connected: {addr}")

    try:
        while True:
            try:
                # readuntil includes the separator (ETX)
                data = await asyncio.wait_for(reader.readuntil(separator=SEPARATOR), timeout=30.0)
            except asyncio.TimeoutError:
                logger.info(f"Read timeout from {addr}, closing connection")
                break
            except asyncio.IncompleteReadError as exc:
                if VERBOSE_DEBUG:
                    logger.debug(f"IncompleteReadError: {exc}")
                logger.info(f"Client {addr} closed connection")
                break
            except Exception as exc:
                logger.warning(f"Read error from {addr}: {type_name(exc)} – {exc}")
                break

            if VERBOSE_DEBUG:
                logger.info(f"Raw data received from {addr}: {data}")

            # strip the trailing ETX for logging/processing, keep original for protocol if needed
            payload = data.rstrip(SEPARATOR)
            if VERBOSE_DEBUG:
                logger.info(f"Raw data (stripped ETX): {payload!r}")

            if payload == b"PING":
                reply_msg = b"ACK:PONG\x03"
                if VERBOSE_DEBUG:
                    logger.debug(f"Send a reply: {reply_msg}")
                writer.write(reply_msg)
                await writer.drain()

            # simple command handling: QUIT causes server to close this connection
            elif payload == b"QUIT":
                reply_msg = b"ACK:QUIT\x03"
                if VERBOSE_DEBUG:
                    logger.debug(f"Send a reply: {reply_msg}")
                writer.write(reply_msg)
                await writer.drain()
                logger.info(f"Closing connection to {addr} on QUIT.")
                break
            else:
                # echo/ack reply and end with ETX so client can readuntil
                reply_msg = b"ACK:" + payload + SEPARATOR
                if VERBOSE_DEBUG:
                    logger.debug(f"Send a reply: {reply_msg}")
                writer.write(reply_msg)
                await writer.drain()

    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception as exc:
            logger.debug(f"{type_name(exc)}: {exc}")

        logger.info(f"Connection closed: {addr}")


async def main(host: str = "127.0.0.1", port: int = 5555):
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows / restricted loops may not support add_signal_handler
            pass

    server = await asyncio.start_server(handle_client, host, port)
    addr = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    logger.info(f"Server listening on {addr}")

    serve_task = asyncio.create_task(server.serve_forever())
    stop_task = asyncio.create_task(stop_event.wait())

    try:
        done, pending = await asyncio.wait({serve_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)

        # cancel any pending task(s)
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    finally:
        # ensure server is closed cleanly
        server.close()
        try:
            await server.wait_closed()
        except Exception as exc:
            logger.debug(f"{type(exc).__name__}: {exc}")
            pass

        # best-effort cancel remaining tasks
        for t in (serve_task, stop_task):
            if not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

    logger.info("Server shutting down")
    await asyncio.sleep(0.1)  # allow log messages to be sent


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.debug("KeyboardInterrupt received.")
        pass
