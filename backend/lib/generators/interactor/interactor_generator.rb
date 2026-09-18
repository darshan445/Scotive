# frozen_string_literal: true

module Interactor
  class InteractorGenerator < Rails::Generators::Base
    source_root File.expand_path("templates", __dir__)

    argument :class_name, type: :string, default: "MyClass"

    def create_interactor_file
      template "interactor_template.rb.erb",
               File.join("app/interactors", "#{file_name}.rb")
    end

    def create_rspec_file
      template "interactor_spec_template.rb.erb",
               File.join("spec/interactors", "#{file_name}_spec.rb")
    end

    private

    def file_name
      class_name.underscore
    end

    def class_name_camelized
      class_name.camelize
    end
  end
end
