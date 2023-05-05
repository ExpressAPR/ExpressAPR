This folder contains the implementation of ExpressAPR.

We recommend the Python glue script (in the [../expapr-cli/](../expapr-cli/) folder) for normal users, because it handles much dirty stuff (e.g., figuring out the classpath) and provides a friendly CLI. 

The ExpressAPR itself is written in pure Java, so it does not depend on a certain benchmark or operating system. The patch compilation step requires JDK 1.8+. The test execution step should work for projects with JUnit 3.x or 4.x test cases on Java 1.5~1.8.



**See [docs/](docs/) for documentation of the core design.**

