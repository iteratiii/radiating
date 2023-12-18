import RPi.GPIO as GPIO
import speech_recognition as sr
import sounddevice
import random

# NLP, audio
import nltk
from nltk.corpus import wordnet as wn

from better_profanity import profanity

from gtts import gTTS # Google Text to Speech

import os           # to make listen/record work
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import pyaudio
import wave

import pronouncing  # to find rhymes
import pydub        # to convert the file to wav
import pygame       # to play and mix audio
import pyinflect    # to inflect synonyms https://spacy.io/universe/project/pyInflect
import re           # to pattern-match and replace punctuation
import random       # to choose from lists of synonyms and rhymes
import spacy        # to get parts of speech
import string       # to get punctuation
import time         # to sleep


# load model for recognizing parts of speech and inflections
nlp = spacy.load("en_core_web_sm")
punctuation = string.punctuation # load punctuation

from pygame import mixer
from pydub import AudioSegment
from pydub.playback import play

pygame.mixer.pre_init(24000, 8, 1, 256)
pygame.init()

# load GPIO 
GPIO.setwarnings(False) # Ignore warnings for now 
GPIO.setmode(GPIO.BCM) # BCM vs Board 
GPIO.setup(26, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(17, GPIO.OUT)

form_1 = pyaudio.paInt16 # 16-bit resolution
chans = 1 # 1 channel
samp_rate = 44100 # 44.1kHz sampling rate
chunk = 8192 #4096 # 2^12 samples for buffer
record_secs = 7 # seconds to record
dev_index = 1 # device index found by p.get_device_info_by_index(ii), changes this 
wav_output_filename = 'sound.wav' # name of .wav file


def untokenize(words):
  """
  Untokenizing a text undoes the tokenizing operation, restoring
  punctuation and spaces to the places that people expect them to be.
  Ideally, `untokenize(tokenize(text))` should be identical to `text`,
  except for line breaks.
  """
  text = ' '.join(words)
  step1 = text.replace("`` ", '"').replace(" ''", '"').replace('. . .',  '...')
  step2 = step1.replace(" ( ", " (").replace(" ) ", ") ")
  step3 = re.sub(r' ([.,:;?!%]+)([ \'"`])', r"\1\2", step2)
  step4 = re.sub(r' ([.,:;?!%]+)$', r"\1", step3)
  step5 = step4.replace(" '", "'").replace(" n't", "n't").replace(
        "can not", "cannot")
  step6 = step5.replace(" ` ", " '")
  return step6.strip()


def overplay(sentences, factor=0.9):
  """
  Take a list of sentences and play them with increasing overlap.
  """

  files = []

  for idx, sentence in enumerate(sentences):
    tts = gTTS(sentence, lang='en', tld='co.in', slow=False) #Provide the string to convert to speech
    tts.save(f'{idx}.wav')
    
    #save string converted to speech as .wav file (it's actually MPEG Audio 2)
    sound_file = AudioSegment.from_mp3(f'{idx}.wav') 
    sound_file.export(f'{idx}.wav', format='wav')

    if(idx==0):
      file_wav = wave.open('0.wav')
      frequency = file_wav.getframerate()
      pygame.mixer.init(frequency=frequency)

    files.append(f'{idx}.wav')

    pygame_sound = pygame.mixer.Sound(files[idx])

    pygame.mixer.Sound.play(pygame_sound)
    GPIO.output(17, GPIO.HIGH)

    length = pygame_sound.get_length()
    time.sleep(length*factor)
    factor = factor / ((idx*0.55)+1)
    GPIO.output(17, GPIO.LOW)


  time.sleep(length+1)
  pygame.mixer.music.stop()


def repronounce(txt):
  """
  Take a text and gradually swap out each of the words with a rhyming
  word of the same syllable count, checking for offensive language 
  and preserving punctuation.
  """

  sentences = []

  words = nltk.word_tokenize(txt)

  # create an empty list for the swapped-out words
  newwords = []

  sentences.append(untokenize(words))

  # for each word, try and replace it with a random word from the list of rhymes
  # if there's no rhymes, leave it as is
  for idx, word in enumerate(words):
    add = False

    # for each word, try and replace it with a random word from the list of rhymes
    try:
      # find the syllables for the current word
      phones = pronouncing.phones_for_word(word)
      sylcount = pronouncing.syllable_count(phones[0])

      # make an empty list to hold rhymes with matching syllable count
      sylmatches = []

      # get full list of rhymes for the lowercased word
      rhymes = pronouncing.rhymes(word)

      # for each rhyme in the list, check if it has the same # syllables and has no apostrophes, and add it to the list
      for rhyme in rhymes:
        rhymephones = pronouncing.phones_for_word(rhyme)
        rhymesylcount = pronouncing.syllable_count(rhymephones[0])
        if(rhymesylcount == sylcount) and not (profanity.contains_profanity(rhyme)):
          sylmatches.append(rhyme)

      word = random.choice(sylmatches)

      add = True
    # could not find a rhyme
    except:
      word = word
      add = False

    # add the word to your new word list
    newwords.append(word)

    allwords = newwords + words[idx+1:]
    if (add):
      sentence = untokenize(allwords)
      sentences.append(sentence)
      print(sentence)

  # for sentence in sentences:
  #   print(sentence)
  return sentences


def remean(txt):
  """
  Take a text and gradually swap out each of the words with a synonym.
  """
  sentences = []
  newwords = []

  words = nltk.word_tokenize(txt)
  doc = nlp(txt)

  # add the original sentence to sentences — I used this previously to match the formatting of all the other sentences.
  sentences.append(untokenize(words))

  for index, token in enumerate(doc):
    word_replaced = False

    # create empty list to hold synonyms
    syns_with_correct_inflection = []
    synonyms = []


    # find its synonyms in wordnet
    for syn in wn.synsets(token.text): 
        for l in syn.lemmas(): 
          # replace underscores with spaces and append to list
          synonym = re.sub("_"," ",l.name())
          synonyms.append(l.name()) 

    # turn them into a flat list
    synonyms = list(set(synonyms))

    # for each synonym, if it's the same part of speech as the original word,
    # inflect it the same as the original and add it to a list
    for synonym in synonyms:

      # turn it into a spacy doc
      syndoc = nlp(synonym)

      # for each token (one word), find synonyms of the same POS
      # inflect them the same as the token, then
      # add it to the list of potential replacements
      for syntok in syndoc:
        if (syntok.pos_ == token.pos_):
          syntok_inflected = syntok._.inflect(token.tag_)

          if (syntok_inflected != None) and (syntok_inflected.lower() != token.text):
            syns_with_correct_inflection.append(syntok_inflected)

    # if list not empty, pick a random synonym
    if syns_with_correct_inflection:
      random_syn = random.choice(syns_with_correct_inflection)
      word = random.choice(syns_with_correct_inflection)
      word_replaced = True

    else:
      word = token.text
      word_replaced = False


    # add the word to your new word list, whether it's been replaced or not
    newwords.append(word)

    # combine the new words on the left and the old words on the right
    allwords = newwords + words[index+1:]

    # if the word was replaced, add it to the sentences
    if word_replaced:
      sentence = untokenize(allwords)
      sentences.append(sentence)
      print(sentence)
    else:
      pass

  return sentences


def recordAudio(): 
  audio = pyaudio.PyAudio() # create pyaudio instantiation

  # create pyaudio stream
  stream = audio.open(format = form_1,rate = samp_rate,channels = chans, \
                      #input_device_index = dev_index,
                      input = True, \
                      frames_per_buffer=chunk)
  print("Listening.")
  GPIO.output(17, GPIO.HIGH)

  frames = []

  # loop through stream and append audio chunks to frame array
  for ii in range(0,int((samp_rate/chunk)*record_secs)):
      data = stream.read(chunk)
      frames.append(data)

  print("Stopped listening.")
  GPIO.output(17, GPIO.LOW)

  # stop the stream, close it, and terminate the pyaudio instantiation
  stream.stop_stream()
  stream.close()
  audio.terminate()

  # save the audio frames as .wav file
  wavefile = wave.open(wav_output_filename,'wb')
  wavefile.setnchannels(chans)
  wavefile.setsampwidth(audio.get_sample_size(form_1))
  wavefile.setframerate(samp_rate)
  wavefile.writeframes(b''.join(frames))
  wavefile.close()


def audioToText():
  # read filename 
  filename = 'sound.wav'

  # initialize the recognizer
  r = sr.Recognizer()

  # open the file
  with sr.AudioFile(filename) as source:
    # listen for the data (load audio to memory)
    audio_data = r.record(source)

    try:
      # recognize (convert from speech to text)
      heard_text = r.recognize_google(audio_data)
      print(heard_text.lower())

      choice = random.randint(0,2)
      if(choice == 0):
        overplay(repronounce(heard_text.lower()))
      else:
        overplay(remean(heard_text.lower()))

    except Exception as e:
      tts = gTTS("i didn't hear", lang='en', tld='co.in', slow=False) #Provide the string to convert to speech
      tts.save('silence.wav')
      
      #save string converted to speech as .wav file (it's actually MPEG Audio 2)
      sound_file = AudioSegment.from_mp3('silence.wav') 
      sound_file.export('silence.wav', format='wav')

      silence = AudioSegment.from_wav("silence.wav")
      play(silence)


while True:
  GPIO.output(17, GPIO.HIGH)
  time.sleep(0.5)

  if GPIO.input(26) == GPIO.LOW:
    try:
      recordAudio()
    except:
      pass  

    # add sleep to make sure file has time to save before code runs
    time.sleep(0.5)

    audioToText()

    time.sleep(0.5)

  GPIO.output(17, GPIO.LOW)
  time.sleep(0.75)

message = input ("Press button and say something short. Press enter to quit. \n")
GPIO.cleanup()