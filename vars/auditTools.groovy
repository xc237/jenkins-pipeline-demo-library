def call() {
    node {
      bat '''
        git version
        dotnet --list-sdks
        dotnet --list-runtimes
      '''
    }
}
