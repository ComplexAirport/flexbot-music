<a name="readme-top"></a>
## About The Project
A simple discord bot which plays music from Youtube

## Features
* Play music - with YouTube link or search phrase
* Queue - add, remove, jump, skip, etc.
* Music player - simple but with all the necessary buttons
* Autosuggestions - helping to search for desired song

## Usage
### Playing music
The music will be playing in the channel that you are currently in
```shell
/play faded # Searches YouTube for 'faded' and plays the first result
/play https://youtu.be/60ItHLz5WEA?si=p4vTpT3IYYk4Q5dX # Play music from link

/queue faded # Add first video with search 'faded' to queue
/queue https://youtu.be/60ItHLz5WEA?si=p4vTpT3IYYk4Q5dX # Add music from link to queue
```
Playing Showcase
<br>
![](https://github.com/ComplexAirport/flexbot-music/blob/master/media/play_showcase.gif)
<br><br>
Queue Showcase
<br>
![](https://github.com/ComplexAirport/flexbot-music/blob/master/media/queue_showcase.gif)

### Searching music
To get detailed YouTube search, simply type
```shell
/search [search phrase]
```

### Controlling music
There are quite a few commands to control the player
```shell
/skip # Skips to the next song in the queue
/jump [n] # Jumps to the n-th song in the queue, all previous songs are removed

/pause # Pauses play
/resume # Resumes play

/remove [n] # Removes n-th song from the queue
/clear # Clears queue and stops playing music

/volume [n] # Sets the volume to n% (relative to the original volume)

/controls # Get music player controls (the buttons)
/status # Get queue and song info without the buttons
/help # Get the help message
```

Remove and jump showcase
<br>
![](https://github.com/ComplexAirport/flexbot-music/blob/master/media/remove_jump_showcase.gif)
<br>

<p align="right">(<a href="#readme-top">back to top</a>)</p>
