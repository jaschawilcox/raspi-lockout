# Access Control on a Raspberry Pi
![Typical Installation](https://cloud.githubusercontent.com/assets/7141976/9291891/e1ae9990-43a7-11e5-9db3-8d20e1cdc4ef.png)

This purpose of this project is to provide a very user-friendly and comparatively low cost machine access control system. Especially in places like machine shops on university campuses, these electronic lockout controllers make it very easy to ensure users are trained prior to using equipment, and keeping track of who uses what and when is made trivial. This project was originally started for [The Construct at RIT](http://hack.rit.edu/)

## Hardware
Typical hardware implementation of a Raspberry Pi running this software with the following peripherals:
- 4x20 LCD for communicating state and messages
- Relay to control machine emergency stop circuit
- USB mag-stripe reader for authenticating ID cards
- USB wifi dongle
- A big red mushroom switch with two contact blocks allows for both hard and soft emergency stop circuit control.
- All of these components are then installed in a sealed project box, making it suitable for use in dusty or wet environments, such as a machine shop. (someting like IP54 rating)

## Core Features
- Unlock using university mag-stripe ID card, lock/end session with e-stop button depression
- Quick and simple administration using google docs, updated every 10 minutes
- Individual control of machine timeout duration, and user access to machine
- UID hashed
- LCD displays current state and status messages. Also shows user who unlocked and remaining session time while machine is unlocked
- Warning alarm 10 minutes before lockout to extend session
- Session can be extended by any authorized user re-swiping ID card
