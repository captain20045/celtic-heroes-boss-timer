import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

DATA_FILE = Path(os.getenv("DATA_DIR", ".")) / "boss_data.json"
TOKEN = os.getenv("DISCORD_TOKEN")

# Default values are EXAMPLES only.
# Use /setboss to set the correct min/max respawn window for your server/event.
DEFAULT_DATA = {
    "bosses": {
        # End Game Bosses
        "CROM": {"min_hours": 96.0, "max_hours": 120.0},
        "DINO": {"min_hours": 34.0, "max_hours": 40.0},
        "BT": {"min_hours": 34.0, "max_hours": 62.0},
        "GELE": {"min_hours": 32.0, "max_hours": 60.0},
        "PROT": {"min_hours": 18.0, "max_hours": 18.25},

        # Mid Game Bosses
        "MORD": {"min_hours": 20.0, "max_hours": 36.0},
        "NECRO": {"min_hours": 22.0, "max_hours": 38.0},
        "HRUNG": {"min_hours": 22.0, "max_hours": 38.0},
        "AGGY": {"min_hours": 20.0, "max_hours": 36.0},

        # EDL Bosses
        "215": {"min_hours": 2.25, "max_hours": 2.333333},
        "210": {"min_hours": 2.083333, "max_hours": 2.166667},

        # DL Bosses
        "180": {"min_hours": 1.466667, "max_hours": 1.516667},
        "170": {"min_hours": 1.3, "max_hours": 1.35},
    },
    "timers": {},
    "alert_channel_id": None,
    "alert_role_id": None
}

def load_data():
    if not DATA_FILE.exists():
        save_data(DEFAULT_DATA.copy())
    with DATA_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def utc_now():
    return datetime.now(timezone.utc)

def discord_ts(dt, style="R"):
    return f"<t:{int(dt.timestamp())}:{style}>"

def boss_key_lookup(data, name):
    for key in data["bosses"]:
        if key.lower() == name.lower():
            return key
    return None

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    if not timer_checker.is_running():
        timer_checker.start()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print("Slash command sync failed:", e)

@bot.tree.command(name="setchannel", description="Set this channel as the boss alert channel.")
@app_commands.checks.has_permissions(manage_guild=True)
async def setchannel(interaction: discord.Interaction):
    data = load_data()
    data["alert_channel_id"] = interaction.channel_id
    save_data(data)
    await interaction.response.send_message(
        f"✅ Boss alerts will be sent to {interaction.channel.mention}.",
        ephemeral=True
    )

@bot.tree.command(name="setrole", description="Set the Discord role to ping for boss alerts.")
@app_commands.describe(role="Role to ping when a boss window starts")
@app_commands.checks.has_permissions(manage_guild=True)
async def setrole(interaction: discord.Interaction, role: discord.Role):
    data = load_data()
    data["alert_role_id"] = role.id
    save_data(data)
    await interaction.response.send_message(
        f"✅ Alert role set to {role.mention}.",
        ephemeral=True
    )

@bot.tree.command(name="setboss", description="Add/update a boss respawn window in minutes.")
@app_commands.describe(
    boss="Boss name",
    min_minutes="Earliest respawn after kill, in minutes",
    max_minutes="Latest respawn after kill, in minutes"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def setboss(
    interaction: discord.Interaction,
    boss: str,
    min_minutes: int,
    max_minutes: int
):
    if min_minutes < 0 or max_minutes < 0:
        await interaction.response.send_message("❌ Minutes cannot be negative.", ephemeral=True)
        return
    if max_minutes < min_minutes:
        await interaction.response.send_message(
            "❌ max_minutes must be greater than or equal to min_minutes.",
            ephemeral=True
        )
        return

    data = load_data()
    existing = boss_key_lookup(data, boss)
    key = existing or boss.strip()

    # Keep internal storage in hours for compatibility with existing timers/config.
    data["bosses"][key] = {
        "min_hours": min_minutes / 60.0,
        "max_hours": max_minutes / 60.0
    }
    save_data(data)

    await interaction.response.send_message(
        f"✅ **{key}** set to **{min_minutes}–{max_minutes} minutes**.",
        ephemeral=True
    )

@bot.tree.command(name="removeboss", description="Remove a boss from the boss list.")
@app_commands.describe(boss="Boss name")
@app_commands.checks.has_permissions(manage_guild=True)
async def removeboss(interaction: discord.Interaction, boss: str):
    data = load_data()
    key = boss_key_lookup(data, boss)
    if not key:
        await interaction.response.send_message("❌ Boss not found.", ephemeral=True)
        return

    data["bosses"].pop(key, None)
    data["timers"].pop(key, None)
    save_data(data)
    await interaction.response.send_message(f"🗑️ Removed **{key}**.", ephemeral=True)

@bot.tree.command(name="kill", description="Record a boss kill and start its respawn timer.")
@app_commands.describe(boss="Boss name")
async def kill(interaction: discord.Interaction, boss: str):
    data = load_data()
    key = boss_key_lookup(data, boss)

    if not key:
        await interaction.response.send_message(
            "❌ Boss not found. An admin can add it with `/setboss`.",
            ephemeral=True
        )
        return

    cfg = data["bosses"][key]
    if cfg["max_hours"] <= 0:
        await interaction.response.send_message(
            f"⚠️ **{key}** does not have a respawn window configured yet. "
            f"Use `/setboss` first.",
            ephemeral=True
        )
        return

    killed_at = utc_now()
    earliest = killed_at + timedelta(hours=cfg["min_hours"])
    latest = killed_at + timedelta(hours=cfg["max_hours"])

    data["timers"][key] = {
        "killed_at": killed_at.isoformat(),
        "earliest": earliest.isoformat(),
        "latest": latest.isoformat(),
        "warn_30_sent": False,
        "warn_10_sent": False,
        "window_sent": False,
        "late_sent": False,
        "killed_by": interaction.user.id
    }
    save_data(data)

    embed = discord.Embed(
        title=f"☠️ {key} killed",
        description=f"Recorded by {interaction.user.mention}"
    )
    embed.add_field(name="Killed", value=discord_ts(killed_at, "F"), inline=False)

    if cfg["min_hours"] == cfg["max_hours"]:
        embed.add_field(
            name="Next spawn",
            value=f"{discord_ts(earliest, 'F')}\n({discord_ts(earliest, 'R')})",
            inline=False
        )
    else:
        embed.add_field(
            name="Spawn window starts",
            value=f"{discord_ts(earliest, 'F')}\n({discord_ts(earliest, 'R')})",
            inline=False
        )
        embed.add_field(
            name="Spawn window ends",
            value=f"{discord_ts(latest, 'F')}\n({discord_ts(latest, 'R')})",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="clear", description="Clear a boss timer.")
@app_commands.describe(boss="Boss name")
async def clear(interaction: discord.Interaction, boss: str):
    data = load_data()
    key = boss_key_lookup(data, boss)
    if not key or key not in data["timers"]:
        await interaction.response.send_message("❌ No active timer found.", ephemeral=True)
        return

    data["timers"].pop(key, None)
    save_data(data)
    await interaction.response.send_message(f"✅ Cleared **{key}** timer.")

async def send_boss_list(interaction: discord.Interaction):
    data = load_data()
    now = utc_now()

    lines = []

    for boss_name, cfg in data["bosses"].items():
        timer = data["timers"].get(boss_name)

        if not timer:
            if cfg["max_hours"] > 0:
                lines.append(f"**{boss_name}** — no active timer")
            else:
                lines.append(f"**{boss_name}** — ⚙️ not configured")
            continue

        earliest = datetime.fromisoformat(timer["earliest"])
        latest = datetime.fromisoformat(timer["latest"])

        if now < earliest:
            remaining = earliest - now
            total_minutes = max(0, int(remaining.total_seconds() // 60))
            hours, minutes = divmod(total_minutes, 60)

            if hours > 0 and minutes > 0:
                remaining_text = f"{hours}h {minutes}m"
            elif hours > 0:
                remaining_text = f"{hours}h"
            else:
                remaining_text = f"{minutes}m"

            lines.append(f"**{boss_name}** — {remaining_text}")

        elif now <= latest:
            remaining = latest - now
            total_minutes = max(0, int(remaining.total_seconds() // 60))
            hours, minutes = divmod(total_minutes, 60)

            if hours > 0 and minutes > 0:
                remaining_text = f"{hours}h {minutes}m left"
            elif hours > 0:
                remaining_text = f"{hours}h left"
            else:
                remaining_text = f"{minutes}m left"

            lines.append(f"**{boss_name}** — **(DUE)** {remaining_text}")

        else:
            lines.append(f"**{boss_name}** — **(OVERDUE)**")

    embed = discord.Embed(
        title="⚔️ Celtic Heroes Boss List",
        description="\n".join(lines) if lines else "No bosses configured."
    )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="bosses", description="Show all configured bosses and active timers.")
async def bosses(interaction: discord.Interaction):
    await send_boss_list(interaction)


@bot.tree.command(name="bosslist", description="Show all configured bosses and active timers.")
async def bosslist(interaction: discord.Interaction):
    await send_boss_list(interaction)


@bot.tree.command(name="nextboss", description="Show the next boss spawn window.")
async def nextboss(interaction: discord.Interaction):
    data = load_data()
    now = utc_now()
    candidates = []

    for boss_name, timer in data["timers"].items():
        earliest = datetime.fromisoformat(timer["earliest"])
        latest = datetime.fromisoformat(timer["latest"])
        if latest >= now:
            candidates.append((earliest, latest, boss_name))

    if not candidates:
        await interaction.response.send_message("No upcoming boss windows.")
        return

    candidates.sort(key=lambda x: x[0])
    earliest, latest, name = candidates[0]

    if now >= earliest:
        msg = (
            f"🔴 **{name}** is currently in its spawn window.\n"
            f"Window ends {discord_ts(latest, 'R')}."
        )
    else:
        msg = (
            f"⏰ Next boss: **{name}**\n"
            f"Window starts {discord_ts(earliest, 'R')} "
            f"({discord_ts(earliest, 'F')})."
        )

    await interaction.response.send_message(msg)

@tasks.loop(seconds=30)
async def timer_checker():
    data = load_data()
    channel_id = data.get("alert_channel_id")
    if not channel_id:
        return

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            return

    role_id = data.get("alert_role_id")
    ping = f"<@&{role_id}> " if role_id else ""
    now = utc_now()
    changed = False

    for boss_name, timer in list(data["timers"].items()):
        killed_at = datetime.fromisoformat(timer["killed_at"])
        earliest = datetime.fromisoformat(timer["earliest"])
        latest = datetime.fromisoformat(timer["latest"])

        total_to_earliest = earliest - killed_at
        warn30 = earliest - timedelta(minutes=30)
        warn10 = earliest - timedelta(minutes=10)

        # Only send a 30m warning if the boss actually has at least a 30m pre-spawn period.
        if (
            total_to_earliest >= timedelta(minutes=30)
            and now >= warn30
            and now < warn10
            and not timer.get("warn_30_sent")
        ):
            await channel.send(
                f"{ping}⏳ **{boss_name}** spawn window starts in about **30 minutes**."
            )
            timer["warn_30_sent"] = True
            changed = True

        # Only send a 10m warning if the boss actually has at least a 10m pre-spawn period.
        if (
            total_to_earliest >= timedelta(minutes=10)
            and now >= warn10
            and now < earliest
            and not timer.get("warn_10_sent")
        ):
            await channel.send(
                f"{ping}⚠️ **{boss_name}** spawn window starts in about **10 minutes**."
            )
            timer["warn_10_sent"] = True
            changed = True

        if now >= earliest and not timer.get("window_sent"):
            if earliest == latest:
                await channel.send(
                    f"{ping}🔥 **{boss_name}** should be spawning now!"
                )
            else:
                await channel.send(
                    f"{ping}🔥 **{boss_name} SPAWN WINDOW STARTED!**"   
                    f"Latest: {discord_ts(latest, 'F')} ({discord_ts(latest, 'R')})"
                )
            timer["window_sent"] = True
            changed = True

        if now > latest and not timer.get("late_sent"):
            await channel.send(
                f"⚫ **{boss_name}** spawn window has passed. "
                f"If it was killed, record it with `/kill {boss_name}`."
            )
            timer["late_sent"] = True
            changed = True

    if changed:
        save_data(data)

@timer_checker.before_loop
async def before_timer_checker():
    await bot.wait_until_ready()

@setchannel.error
@setrole.error
@setboss.error
@removeboss.error
async def admin_command_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        if interaction.response.is_done():
            await interaction.followup.send(
                "❌ You need **Manage Server** permission for this command.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ You need **Manage Server** permission for this command.",
                ephemeral=True
            )
    else:
        raise error

if not TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing. Set it as an environment variable before running the bot."
    )

bot.run(TOKEN)
