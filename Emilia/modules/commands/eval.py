import asyncio
import io
import os
import sys
import traceback

from pyrogram.enums import ParseMode
from pyrogram.types import ReplyParameters

from Emilia.custom_filter import auth


@auth(pattern="exec")
async def __exec(client, message):
    # DEV_USERS-gated by the @auth decorator above — do not loosen.
    try:
        cmd = message.text.split(maxsplit=1)[1]
    except IndexError:
        return await message.reply_text("`Usage: `/exec <code>")
    msg = await message.reply_text("`Executing...`")
    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    result = str(stdout.decode().strip()) + str(stderr.decode().strip())
    cresult = f"<b>Bash:~#</b> <code>{cmd}</code>\n<b>Result:</b> <code>{result}</code>"
    if len(str(cresult)) > 4090:
        with io.BytesIO(result.encode()) as file:
            file.name = "bash.txt"
            await message.reply_document(
                file, caption=f"<code>{cmd}</code>", parse_mode=ParseMode.HTML
            )
            return await msg.delete()
    try:
        await msg.edit_text(cresult, parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(str(e))


@auth(pattern="eval")
async def eval_e(client, message):
    # DEV_USERS-gated by the @auth decorator above — do not loosen.
    try:
        cmd = message.text.split(None, 1)[1]
    except IndexError:
        return await message.reply_text("`Usage: /eval <python_code>`")

    xx = await message.reply_text("`Processing..`")
    if message.reply_to_message_id:
        reply_to_id = message.reply_to_message_id
    old_stderr = sys.stderr
    old_stdout = sys.stdout
    redirected_output = sys.stdout = io.StringIO()
    redirected_error = sys.stderr = io.StringIO()
    stdout, stderr, exc = None, None, None
    reply_to_id = message.id
    try:
        await aexec(cmd, client, message)
    except Exception:
        exc = traceback.format_exc()
    stdout = redirected_output.getvalue()
    stderr = redirected_error.getvalue()
    sys.stdout = old_stdout
    sys.stderr = old_stderr
    evaluation = ""
    if exc:
        evaluation = exc
    elif stderr:
        evaluation = stderr
    elif stdout:
        evaluation = stdout
    else:
        evaluation = "Success"
    final_output = (
        f"**EVAL**\n```{cmd}``` \n\n __►__ **OUTPUT**: \n```{evaluation}``` \n"
    )

    if len(final_output) > 4096:
        lmao = final_output.replace("`", "").replace("**", "").replace("__", "")
        with io.BytesIO(str.encode(lmao)) as out_file:
            out_file.name = "eval.txt"
            await client.send_document(
                message.chat.id,
                out_file,
                caption=f"```{cmd}```" if len(cmd) < 998 else None,
                reply_parameters=ReplyParameters(message_id=reply_to_id),
            )
            await xx.delete()
    else:
        await xx.edit_text(final_output)


async def aexec(code, client, message):
    # both `message` and `event` are bound to the pyrogram message so old
    # snippets work
    exec(
        (
            (
                ("async def __aexec(e, client): " + "\n message = event = e")
                + "\n r = event.reply_to_message"
            )
            + ("\n chat = event.chat.id")
            + "\n p = print"
        )
        + "".join(f"\n {l}" for l in code.split("\n"))
    )

    return await locals()["__aexec"](message, client)


@auth(pattern="restart")
async def _(client, message):
    await message.reply_text("`Restarting..`")
    os.execv(sys.executable, ["python3", "-m", "Emilia"])


@auth(pattern="logs")
async def _logs(client, message):
    await message.reply_document("log.txt")
