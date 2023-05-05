package expressapr.igniter;

import com.github.javaparser.ast.Node;
import com.github.javaparser.printer.configuration.DefaultConfigurationOption;
import com.github.javaparser.printer.configuration.DefaultPrinterConfiguration;
import com.github.javaparser.printer.configuration.PrinterConfiguration;
import com.github.javaparser.printer.lexicalpreservation.LexicalPreservingPrinter;

public class TreeStringify {
    private static PrinterConfiguration conf;

    static void setup(Node node) {
        if(Args.USE_LEXICAL_PRINTING) {
            LexicalPreservingPrinter.setup(node);
        } else {
            conf = new DefaultPrinterConfiguration();
            conf.addOption(new DefaultConfigurationOption(DefaultPrinterConfiguration.ConfigOption.PRINT_COMMENTS));
            conf.addOption(new DefaultConfigurationOption(DefaultPrinterConfiguration.ConfigOption.PRINT_JAVADOC));
        }
    }

    static String print(Node node) {
        if(Args.USE_LEXICAL_PRINTING)
            return LexicalPreservingPrinter.print(node);
        else
            return node.toString(conf);
    }
}
