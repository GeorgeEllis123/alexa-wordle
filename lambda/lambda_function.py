# -*- coding: utf-8 -*-

from random import *
import logging
import os
import boto3

from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput

from ask_sdk_model import Response
from ask_sdk_dynamodb.adapter import DynamoDbAdapter

SKILL_NAME = 'wordle'
ddb_region = os.environ.get('DYNAMODB_PERSISTENCE_REGION')
ddb_table_name = os.environ.get('DYNAMODB_PERSISTENCE_TABLE_NAME')
ddb_resource = boto3.resource('dynamodb', region_name=ddb_region)
dynamodb_adapter = DynamoDbAdapter(table_name=ddb_table_name, create_table=False, dynamodb_resource=ddb_resource)
sb = CustomSkillBuilder(persistence_adapter=dynamodb_adapter)

def _load_apl_document(file_path):
    # type: (str) -> Dict[str, Any]
    # Load the apl json document at the path into a dict object.
    with open(file_path) as f:
        return json.load(f)
    
from ask_sdk_model.interfaces.alexa.presentation.apl import (
	    RenderDocumentDirective, ExecuteCommandsDirective, SpeakItemCommand,
	    AutoPageCommand, HighlightMode)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def readFile(filename):
    fileContents = open(filename, "r")
    contents = []
    for line in fileContents:
        line = line.strip()
        contents.append(line)

    return contents

def checkGuess(guess, answer, clues, numGuesses):
    clue = []
    lettersSeen = ""
    for i in range(len(guess)):
        gChar = guess[i]
        aChar = answer[i]
        if gChar == aChar:
            clue.append('=')
            lettersSeen += gChar
        else:
            clue.append('_')

    for i in range(len(guess)):
        gChar = guess[i]
        aChar = answer[i]
        if gChar == aChar:
            clue[i] = '='
        elif gChar in answer and gChar not in lettersSeen:
            clue[i] = ('+')
            lettersSeen += gChar
        else:
            clue[i] = ('_')
    
    clueStr = ""

    clues[numGuesses] = clueStr.join(clue)
    return clues 

@sb.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_request_handler(handler_input):
    """Handler for Skill Launch.

    Get the persistence attributes, to figure out the game state.
    """
    # type: (HandlerInput) -> Response
    attr = handler_input.attributes_manager.persistent_attributes
    if not attr:
        attr['ended_session_count'] = 0
        attr['games_played'] = 0
        attr['game_state'] = 'ENDED'

    handler_input.attributes_manager.session_attributes = attr

    speech_text = (
        "Welcome to Wordle. You have played {} times. "
        "Would you like to play?".format(attr["games_played"]))
    reprompt = "Say yes to start the game or no to quit."

    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_intent_name("AMAZON.HelpIntent"))
def help_intent_handler(handler_input):
    """Handler for Help Intent."""
    # type: (HandlerInput) -> Response
    speech_text = (
        "I am thinking of a five letter word, try to guess it and I will give you hints")
    reprompt = "Try saying a word."

    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(
    can_handle_func=lambda input:
        is_intent_name("AMAZON.CancelIntent")(input) or
        is_intent_name("AMAZON.StopIntent")(input))
def cancel_and_stop_intent_handler(handler_input):
    """Single handler for Cancel and Stop Intent."""
    # type: (HandlerInput) -> Response
    speech_text = "Thanks for playing!!"

    handler_input.response_builder.speak(
        speech_text).set_should_end_session(True)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=is_request_type("SessionEndedRequest"))
def session_ended_request_handler(handler_input):
    """Handler for Session End."""
    # type: (HandlerInput) -> Response
    logger.info(
        "Session ended with reason: {}".format(
            handler_input.request_envelope.request.reason))
    return handler_input.response_builder.response


def currently_playing(handler_input):
    """Function that acts as can handle for game state."""
    # type: (HandlerInput) -> bool
    is_currently_playing = False
    session_attr = handler_input.attributes_manager.session_attributes

    if ("game_state" in session_attr
            and session_attr['game_state'] == "STARTED"):
        is_currently_playing = True

    return is_currently_playing


@sb.request_handler(can_handle_func=lambda input:
                    not currently_playing(input) and
                    is_intent_name("AMAZON.YesIntent")(input))
def yes_handler(handler_input):
    """Handler for Yes Intent, only if the player said yes for
    a new game.
    """
    # type: (HandlerInput) -> Response
    session_attr = handler_input.attributes_manager.session_attributes
    session_attr['game_state'] = "STARTED"
    session_attr['no_of_guesses'] = 0
    session_attr['all_clues'] = ["_____","_____","_____","_____","_____","_____"]
    session_attr['attempted_words'] = ["_____","_____","_____","_____","_____","_____"]
    
    possibleAnswers = readFile("answers.txt")
    session_attr['guess_word'] = choice(possibleAnswers)
    
    possibleGuesses = readFile("five-letter-words.txt")
    session_attr['guessing_words'] = possibleGuesses
    

    speech_text = "Great! Try saying a {} to start the game.".format(session_attr['guess_word'])
    reprompt = "Try saying a real five letter word."
    
    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    not currently_playing(input) and
                    is_intent_name("AMAZON.NoIntent")(input))
def no_handler(handler_input):
    """Handler for No Intent, only if the player said no for
    a new game.
    """
    # type: (HandlerInput) -> Response
    session_attr = handler_input.attributes_manager.session_attributes
    session_attr['game_state'] = "ENDED"
    session_attr['ended_session_count'] += 1

    handler_input.attributes_manager.persistent_attributes = session_attr
    handler_input.attributes_manager.save_persistent_attributes()

    speech_text = "Ok. See you next time!!"

    handler_input.response_builder.speak(speech_text)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    currently_playing(input) and
                    is_intent_name("WordGuessIntent")(input))
def word_guess_handler(handler_input):
    """Handler for processing guess with target."""
    # type: (HandlerInput) -> Response
    session_attr = handler_input.attributes_manager.session_attributes
    target_word = session_attr["guess_word"]
    clues = session_attr["all_clues"]
    
    guess_w = str(handler_input.request_envelope.request.intent.slots["word"].value)
    
    guess_num = session_attr["no_of_guesses"]
    session_attr["no_of_guesses"] += 1
    
    if guess_w == target_word:
        speech_text = "{} was the word! Congrats you won in {} guesses".format(target_word, str(guess_num+1))
        reprompt = "Would you like to play again?"
    else:
        
        session_attr["all_clues"] = checkGuess(guess_w, target_word, clues, guess_num)
        
        new_clues = session_attr["all_clues"]
        
        speech_text = "{} is your guess. {} is your new clue.".format(guess_w, new_clues[guess_num])
        reprompt = "Guess a real five letter word"

    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input:
                    is_intent_name("AMAZON.FallbackIntent")(input) or
                    is_intent_name("AMAZON.YesIntent")(input) or
                    is_intent_name("AMAZON.NoIntent")(input))
def fallback_handler(handler_input):
    """AMAZON.FallbackIntent is only available in en-US locale.
    This handler will not be triggered except in that locale,
    so it is safe to deploy on any locale.
    """
    # type: (HandlerInput) -> Response
    session_attr = handler_input.attributes_manager.session_attributes

    if ("game_state" in session_attr and
            session_attr["game_state"]=="STARTED"):
        speech_text = (
            "The {} skill can't help you with that.  "
            "Try guessing a five letter word".format(SKILL_NAME))
        reprompt = "Please guess a five letter word."
    else:
        speech_text = (
            "The {} skill can't help you with that.  "
            "It will come up with a five letter word "
            "you try to guess it.                    "
            "Would you like to play?".format(SKILL_NAME))
        reprompt = "Say yes to start the game or no to quit."

    handler_input.response_builder.speak(speech_text).ask(reprompt)
    return handler_input.response_builder.response


@sb.request_handler(can_handle_func=lambda input: True)
def unhandled_intent_handler(handler_input):
    """Handler for all other unhandled requests."""
    # type: (HandlerInput) -> Response
    speech = "Say yes to continue or no to end the game!!"
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response


@sb.exception_handler(can_handle_func=lambda i, e: True)
def all_exception_handler(handler_input, exception):
    """Catch all exception handler, log exception and
    respond with custom message.
    """
    # type: (HandlerInput, Exception) -> Response
    logger.error(exception, exc_info=True)
    speech = "Sorry, I can't understand that. Please say again!!"
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response


@sb.global_response_interceptor()
def log_response(handler_input, response):
    """Response logger."""
    # type: (HandlerInput, Response) -> None
    logger.info("Response: {}".format(response))


lambda_handler = sb.lambda_handler()
