def call() {
      bat '''
        git version
        dotnet --list-sdks
        dotnet --list-runtimes
        dir m3
      '''
}
