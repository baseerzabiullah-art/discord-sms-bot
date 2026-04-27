import discord
from discord.ext import commands
import aiohttp
import os
import asyncio
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
user_credentials = {}

class APIModal(discord.ui.Modal, title="SMSPool API Key"):
    api_key = discord.ui.TextInput(label="Enter your SMSPool API Key", placeholder="Your API key here", required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        api_key = str(self.api_key)
        
        if user_id not in user_credentials:
            user_credentials[user_id] = {}
        user_credentials[user_id]["api_key"] = api_key
        
        embed = discord.Embed(
            title="✅ API Key Saved",
            description="Your SMSPool API key has been saved successfully!",
            color=discord.Color.green()
        )
        
        view = PlatformView(user_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PlatformView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    
    @discord.ui.button(label="Normal SMS", style=discord.ButtonStyle.primary)
    async def normal_sms(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        user_id = interaction.user.id
        if user_id not in user_credentials or "api_key" not in user_credentials[user_id]:
            await interaction.followup.send("❌ API key not found. Please try again.", ephemeral=True)
            return
        
        api_key = user_credentials[user_id]["api_key"]
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.smspool.net/request"
                params = {
                    "key": api_key,
                    "country": "US",
                    "service": "discord"
                }
                
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("success"):
                            phone_number = data.get("phonenumber")
                            request_id = data.get("request_id")
                            
                            if user_id not in user_credentials:
                                user_credentials[user_id] = {}
                            user_credentials[user_id]["current_request"] = {
                                "request_id": request_id,
                                "phone": phone_number,
                                "api_key": api_key
                            }
                            
                            embed = discord.Embed(
                                title="📱 SMS Number Generated",
                                description=f"**Phone Number:** `{phone_number}`\n\nWaiting for SMS...",
                                color=discord.Color.green()
                            )
                            
                            msg = await interaction.followup.send(embed=embed, ephemeral=True)
                            
                            user_credentials[user_id]["current_request"]["message_id"] = msg.id
                            user_credentials[user_id]["current_request"]["channel_id"] = interaction.channel_id
                            
                            await poll_single_sms(user_id, msg, interaction)
                        else:
                            error = data.get("error", "Unknown error")
                            embed = discord.Embed(
                                title="❌ Error",
                                description=f"Failed to generate SMS: {error}",
                                color=discord.Color.red()
                            )
                            await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        embed = discord.Embed(
                            title="❌ API Error",
                            description=f"SMSPool API error: {resp.status}",
                            color=discord.Color.red()
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Error: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

class MainPanel(discord.ui.View):
    @discord.ui.button(label="Generate SMS", style=discord.ButtonStyle.green)
    async def generate_sms(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        modal = APIModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="SMS Log", style=discord.ButtonStyle.blurple)
    async def sms_log(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        
        if user_id not in user_credentials or "sms_history" not in user_credentials[user_id]:
            embed = discord.Embed(
                title="📋 SMS Log",
                description="No SMS history yet.",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        history = user_credentials[user_id]["sms_history"]
        
        embed = discord.Embed(
            title="📋 SMS Log",
            color=discord.Color.blue()
        )
        
        for i, sms in enumerate(history[-10:], 1):
            embed.add_field(
                name=f"SMS #{len(history) - 10 + i}",
                value=f"**Phone:** `{sms['phone']}`\n**Message:** {sms['message']}\n**Time:** {sms['time']}",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def poll_single_sms(user_id, msg, interaction):
    """Poll for a single SMS"""
    for _ in range(60):
        await asyncio.sleep(5)
        
        if user_id not in user_credentials or "current_request" not in user_credentials[user_id]:
            break
        
        creds = user_credentials[user_id]["current_request"]
        api_key = creds.get("api_key")
        request_id = creds.get("request_id")
        phone = creds.get("phone")
        
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://api.smspool.net/check"
                params = {
                    "key": api_key,
                    "request_id": request_id
                }
                
                async with session.get(url, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        if data.get("success") and data.get("sms"):
                            sms_text = data.get("sms")
                            
                            embed = discord.Embed(
                                title="📨 SMS Received!",
                                description=f"**Phone:** `{phone}`\n\n**Message:**\n{sms_text}",
                                color=discord.Color.green()
                            )
                            
                            await msg.edit(embed=embed)
                            
                            if user_id not in user_credentials:
                                user_credentials[user_id] = {}
                            if "sms_history" not in user_credentials[user_id]:
                                user_credentials[user_id]["sms_history"] = []
                            
                            user_credentials[user_id]["sms_history"].append({
                                "phone": phone,
                                "message": sms_text,
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                            
                            del user_credentials[user_id]["current_request"]
                            break
                        
                        elif data.get("status") == "expired":
                            embed = discord.Embed(
                                title="⏰ Request Expired",
                                description="The SMS request has expired. Please try again.",
                                color=discord.Color.orange()
                            )
                            await msg.edit(embed=embed)
                            del user_credentials[user_id]["current_request"]
                            break
        except Exception as e:
            print(f"Error polling SMS: {e}")

@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")

@bot.command(name="panel")
async def panel(ctx):
    """Create the SMS panel"""
    embed = discord.Embed(
        title="📱 SMS Generator",
        description="Click a button below to get started!",
        color=discord.Color.blue()
    )
    embed.add_field(name="Generate SMS", value="Get a temporary SMS number", inline=False)
    embed.add_field(name="SMS Log", value="View your SMS history", inline=False)
    
    view = MainPanel()
    await ctx.send(embed=embed, view=view)

bot.run(DISCORD_TOKEN)
