# coding=utf8
import traceback, sys, re, time, threading, Queue, socket

import Irc, Config, Transactions, Commands, Config, Global

hooks = {}

def end_of_motd(instance, *_):
	Global.instances[instance].send_lock.release()
	for channel in Config.config["instances"][instance]:
		Irc.instance_send(instance, "JOIN", channel)
hooks["376"] = end_of_motd

def ping(instance, *_):
	Irc.instance_send(instance, "PONG")
hooks["PING"] = ping

class Request(object):
	def __init__(self, instance, target, source, text):
		self.instance = instance
		self.target = target
		self.source = source
		self.nick = Irc.get_nickname(source)
		self.text = text

	def privmsg(self, targ, text):
		while len(text) > 350:
			Irc.instance_send(self.instance, "PRIVMSG", targ, text[:349])
			text = text[350:]
		Irc.instance_send(self.instance, "PRIVMSG", targ, text)

	def reply(self, text):
		self.privmsg(self.target, self.nick + ": " + text)

	def reply_private(self, text):
		self.privmsg(self.nick, self.nick + ": " + text)

	def say(self, text):
		self.privmsg(self.target, text)

def run_command(cmd, req, arg):
	try:
		cmd(req, arg)
	except Exception as e:
		req.reply(repr(e))
		type, value, tb = sys.exc_info()
		print(req.instance + " " + req.text + " ===============")
		traceback.print_tb(tb)
		print(repr(e))
		print(req.instance + " " + req.text + " ===============")

def message(instance, source, target, text):
	host = Irc.get_host(source)
	if host == "lucas.fido.pw":
		m = re.match(r"Wow!  (\S*) just sent you Ð\d*\.", text)
		if not m:
			m = re.match(r"Wow!  (\S*) sent Ð\d* to Doger!", text)
		if m:
			nick = m.group(1)
			address = Transactions.deposit_address(Irc.toupper(nick))
			serv.send("PRIVMSG", "fido", "withdraw " + address.encode("utf8"))
			serv.send("PRIVMSG", nick, "Your tip has been withdrawn to your account and will appear in %balance soon")
	elif text[0] == '%' or target == instance:
		if Irc.is_ignored(host):
			print(instance + ": (ignored) <" + Irc.get_nickname(source) + "> " + text)
			return
		print(instance + ": <" + Irc.get_nickname(source) + "> " + text)
		t = time.time()
		score = Global.flood_score.get(host, (t, 0))
		score = max(score[1] + score[0] - t, 0) + 10
		if score > 80 and not Irc.is_admin(source):
			Irc.ignore(host, 240)
			Irc.instance_send(instance, "PRIVMSG", Irc.get_nickname(source), "You're sending commands too quickly. Your host is ignored for 240 seconds")
			return
		Global.flood_score[host] = (t, score)
		if text[0] == '%':
			text = text[1:]
		src = Irc.get_nickname(source)
		if target == instance:
			reply = src
		else:
			reply = target
		if text.find(" ") == -1:
			command = text
			args = []
		else:
			command, args = text.split(" ", 1)
			args = args.split(" ")
		if command[0] != '_':
			cmd = Commands.commands.get(command, None)
			if not cmd.__doc__ or cmd.__doc__.find("admin") == -1 or Irc.is_admin(source):
				if cmd:
					req = Request(instance, reply, source, text)
					t = threading.Thread(target = run_command, args = (cmd, req, args))
					t.start()
hooks["PRIVMSG"] = message

def error(serv, *_):
	raise socket.error()
hooks["ERROR"] = error

def whois_ident(instance, _, __, target, account, ___):
	Global.instances[instance].lastwhois = account
hooks["330"] = whois_ident

def whois_end(instance, _, __, target, ___):
	try:
		nick, q = Global.instances[instance].whois_queue.get(False)
		if Irc.equal_nicks(target, nick):
			q.put(Global.instances[instance].lastwhois, True)
		else:
			print(instance + ": WHOIS reply for " + target + " but queued " + nick + " returning None")
			q.put(None, True)
		Global.instances[instance].lastwhois = None
		Global.instances[instance].whois_queue.task_done()
	except Queue.Empty:
		print(instance + ": WHOIS reply but nothing queued")
hooks["318"] = whois_end
